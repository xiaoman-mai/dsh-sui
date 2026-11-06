// ============================================================================
// dsh-sui —— 三层记忆：记录 / 记忆 / 感觉
// 工具层只是壳，逻辑在 sui.py（SQLite + 命令行），这里用子进程调它。
// ============================================================================
import { join, dirname } from 'node:path'
import { createRequire } from 'node:module'
import * as fsMod from 'node:fs'
import { execFile } from 'node:child_process'
import { writeFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'

// 包自己所在的目录——引擎 sui.py 就在旁边，别人装的时候不用另外拷一份
const __dirname_of_index = dirname(fileURLToPath(import.meta.url))

export const name = 'dsh-sui'
export const inject = ['tools', 'systemPrompt', 'agents', 'webServer', 'tokenMeter']

// Config：让错字段名当场报错，而不是静默失效。
// schemastery 从 profile 目录解析——包本身是 link 进来的，直接 import 找不到。
let z = null
try {
  const dir = process.env.DSH_PROFILE_DIR
  if (dir) {
    const req = createRequire(join(dir, 'package.json'))
    const resolved = req.resolve('@deepseek-ai/schemastery')
    const mod = await import('file:///' + resolved.replace(/\\/g, '/'))
    z = mod.default || mod
  }
} catch {
  z = null
}

export const Config = z ? z.object({
  workspace: z.string().description('工作区路径'),
  python: z.string().description('python 解释器'),
  script: z.string().description('sui.py 路径'),
  presets: z.array(z.string()).description('只给这些预设挂自动注入'),
  scopeWorkspaces: z.array(z.string()).description('只在这些工作区里挂自动注入；空 = 不限'),
  pressureMid: z.natural().description('上下文到几成开始提醒'),
  pressureHigh: z.natural().description('上下文到几成就自动落盘'),
  recallItems: z.natural().description('每轮注入几条记忆'),
  voiceItems: z.natural().description('每轮注入几个语气词'),
  maxChars: z.natural().description('注入段字数上限'),
  autoRecord: z.boolean().description('自动落盘开关'),
  autoRecordBatch: z.natural().description('一次最多落几条'),
  refreshMs: z.natural().description('缓存刷新间隔（毫秒）'),
}) : undefined

// 路径优先取环境变量，其次工作区配置；只有都没有才落到这台机器的老路径上。
const DEFAULT_WORKSPACE = process.env.DSH_sui_WORKSPACE
  || process.env.DSH_WORKSPACE
  || process.cwd()
const DEFAULT_PYTHON = process.env.DSH_sui_PYTHON
  || 'C:/Users/张锴/.dsh/dsh-runtimes/dsh-primary-runtime/dependencies/python/python.exe'

function log(msg) {
  try { console.log('[dsh-sui] ' + msg) } catch { /* ignore */ }
}

export async function apply(ctx, config) {
  const cfg = { ...(config || {}) }
  const cfgBase = { ...(config || {}) }   // 宿主给的配置，不被 settings 覆盖
  const ws = cfg.workspace || DEFAULT_WORKSPACE
  // ---- 面板里能改的参数：存在 settings.json，优先于 cordis config ----
  const SETTINGS_FILE = join(ws, 'tools', 'sui', 'settings.json')
  // 人 ↔ 记忆库。一个人 = 名字 + 认哪几个预设 + 工作区 + 库。
  // 记忆是跟着人走的，不是跟着目录走的：同一个我换个工作区还是我，
  // 同一个目录里坐两个人也不该共用一个库。
  const PEOPLE_FILE = join(process.env.DSH_PROFILE_DIR || ws, 'sui-people.json')
  function loadPeople() {
    try {
      const j = JSON.parse(fsMod.readFileSync(PEOPLE_FILE, 'utf8'))
      if (j && Array.isArray(j.people)) return j
    } catch { /* 还没建过 */ }
    return { people: [] }
  }
  function savePeople(j) {
    try {
      fsMod.writeFileSync(PEOPLE_FILE, JSON.stringify(j, null, 2), 'utf8')
      return true
    } catch { return false }
  }
  // 按会话的预设认出这是谁
  function personOf(agent) {
    let pr = ''
    try { pr = presetOf(agent) } catch { pr = '' }
    if (!pr) return null
    for (const p of loadPeople().people || []) {
      if (Array.isArray(p.presets) && p.presets.indexOf(pr) >= 0) return p
    }
    return null
  }
  const defaultDbFor = (workspace) => join(workspace || ws, 'tools', 'sui', 'sui.db')
  // 按工作区找库（没有人认得出来时的兜底）
  function dbForWorkspace(workspace) {
    const w = String(workspace || ws).replace(/\\/g, '/').toLowerCase()
    for (const p of loadPeople().people || []) {
      if (!p.db) continue
      const pw = String(p.workspace || '').replace(/\\/g, '/').toLowerCase()
      if (pw && pw === w) return p.db
    }
    const own = defaultDbFor(workspace || ws)
    // 那个工作区自己还没有库，就别在那儿造一个空的出来——
    // 用一个不存在的路径去读，账面上会显示 0 条，看着像把记忆弄丢了。
    try { if (fsMod.existsSync(own)) return own } catch { }
    return defaultDbFor(ws)
  }
  // 认人优先：先看这个会话是哪个预设，认出是谁就用谁的库
  function dbForAgent(agent) {
    try {
      const p = personOf(agent)
      if (p && p.db) return p.db
    } catch { /* 认不出来就走工作区 */ }
    return dbForWorkspace(workspaceOf(agent))
  }
  const DEFAULTS = {
    pressureMid: 55, pressureHigh: 75,
    autoRecord: true, autoRecordBatch: 6,
    recallItems: 3, voiceItems: 3, maxChars: 700,
    decayThreshold: 0.2, loadWindowDays: 30, decayPower: 0.5,
  }
  // 参数按库分开：每个人的阈值可以不一样，settings.json 就放在库文件旁边。
  const settingsByDb = new Map()
  function settingsPathFor(db) {
    return join(dirname(String(db || defaultDbFor(ws))), 'settings.json')
  }
  function settingsFor(db) {
    const key = normDb(db)
    if (settingsByDb.has(key)) return settingsByDb.get(key)
    let j = {}
    try { j = JSON.parse(fsMod.readFileSync(settingsPathFor(db), 'utf8')) || {} } catch { /* 没设过 */ }
    const v = Object.assign({}, DEFAULTS, cfgBase, j)
    settingsByDb.set(key, v)
    return v
  }
  function loadSettings() {
    try {
      const raw = fsMod.readFileSync(SETTINGS_FILE, 'utf8')
      const j = JSON.parse(raw)
      return (j && typeof j === 'object') ? j : {}
    } catch { return {} }
  }
  function saveSettings(next) {
    try {
      fsMod.writeFileSync(SETTINGS_FILE, JSON.stringify(next, null, 1), 'utf8')
      return true
    } catch { return false }
  }
  // settings 覆盖 cordis config
  Object.assign(cfg, DEFAULTS, loadSettings(), config || {})
  // 但 config 里的显式值不该盖掉 settings —— 重新把 settings 盖回来
  Object.assign(cfg, DEFAULTS, config || {}, loadSettings())
  const py = cfg.python || DEFAULT_PYTHON
  // 脚本优先用包里自带的（别人装的时候不用另外拷一份），找不到才回落到工作区
  const bundled = join(__dirname_of_index, 'sui.py')
  const script = cfg.script || (fsMod.existsSync(bundled) ? bundled : join(ws, 'tools', 'sui', 'sui.py'))

  log('apply 进入，脚本 ' + script)

  const tools = ctx.tools || (typeof ctx.get === 'function' ? ctx.get('tools') : undefined)
  const hasTools = !!tools && typeof tools.register === 'function'
  // 拿不到 tools 只跳过工具注册，别把路由、自动注入、自动落盘一起带走
  if (hasTools) log('拿到 tools 服务')
  else log('没有 tools 服务：只跳过工具注册，其余照常')

  // opt.db：这次跑在哪个库上。不给就按「发起这次调用的会话在哪个工作区」来选；
  // 再选不出来才用脚本默认的（同目录 sui.db）。
  // 用 rt 兜一层：agents 服务在后面才拿到，这里先留个位置，避免读到未初始化的变量。
  const rt = { agents: null }
  function run(args, timeoutMs = 20000, opts) {
    let db = opts && opts.db ? String(opts.db) : ''
    if (!db && rt.agents) {
      try {
        const a = rt.agents.currentInitiator ? rt.agents.currentInitiator() : null
        if (a) db = dbForAgent(a)
      } catch { /* 定时器里没有发起者，就用默认库 */ }
    }
    const argv = db ? [script, '--db', db, ...args] : [script, ...args]
    return new Promise((resolve) => {
      execFile(py, argv, {
        cwd: ws,
        timeout: timeoutMs,
        maxBuffer: 4 * 1024 * 1024,
        env: { ...process.env, PYTHONIOENCODING: 'utf-8' },
        windowsHide: true,
      }, (err, stdout, stderr) => {
        const out = (stdout || '').trim()
        const errOut = (stderr || '').trim()
        // 失败要看得见：stderr 有内容、或进程出错，都在结果前面挂标记
        if (errOut && !out) { resolve('⚠️ 失败：' + errOut.split('\n')[0]); return }
        if (out && err) { resolve(out + '\n⚠️ 进程退出异常：' + err.message); return }
        if (!out && err) { resolve('⚠️ 失败：' + err.message); return }
        resolve(out || '（没有输出）')
      })
    })
  }

  const textOut = (description) => ({
    schema: { type: 'string', description },
    render(_args, value) {
      return [{ type: 'text', text: typeof value === 'string' ? value : JSON.stringify(value, null, 2) }]
    },
  })

  const toolOffs = []
  function reg(def) {
    if (!hasTools) return
    try {
      const off = tools.register(def)
      if (typeof off === 'function') toolOffs.push(off)
      log('已注册 ' + def.name)
    } catch (e) {
      log('注册失败 ' + def.name + ' :: ' + (e && e.message ? e.message : e))
    }
  }
  try {
    ctx.effect(() => () => {
      for (const off of toolOffs.splice(0)) { try { off() } catch { } }
    })
  } catch { }

  const str = (description) => ({ type: 'string', description })
  const num = (description) => ({ type: 'number', description })

  reg({
    name: 'sui_fact',
    description: '记录层：记一条发生过的事。什么都能记，像日记。带日期、出处、原文（防止概述顶替原文）和可信度（感觉/推断/转述/亲历，默认推断）。',
    parameters: {
      type: 'object',
      properties: {
        text: str('一句话概述'),
        quote: str('原文/原话（可选，涉及别人说的话时尽量带上）'),
        source: str('出处：链接、文件名、对话日期'),
        from: str('可信度：感觉/推断/转述/亲历，默认推断'),
        date: str('补记历史日期 YYYY-MM-DD（可选，默认今天）'),
        who: str('这条是谁的事（可选，默认 me；一个库混着几个人的时候用）'),
      },
      required: ['text'],
    },
    output: textOut('写入结果'),
    timeoutMs: 30000,
    execute: async (args) => {
      const a = ['fact', args.text]
      if (args.quote) a.push('--quote', args.quote)
      if (args.source) a.push('--source', args.source)
      if (args.from) a.push('--from', args.from)
      if (args.date) a.push('--date', args.date)
      if (args.who) a.push('--who', args.who)
      return await run(a)
    },
  })

  reg({
    name: 'sui_memory',
    description: '记忆层：从记录里提炼一条记忆。必须挂记录编号，必须带感觉词。词表只是常用的锚，不是边界——一个字装不下时可以用短语。写完是「等旁听」——要另一份独立提炼对上才进人格。建议同时给坐标：root 是七情一格，desire 是六欲一条。',
    parameters: {
      type: 'object',
      properties: {
        text: str('提炼出来的一句话'),
        src: str('证据编号，逗号分隔，例如 "3,5"'),
        feel: str('感觉词，逗号分隔，例如 "安,暖"'),
        root: str('七情一格：喜 怒 忧 思 悲 恐 惊 平（可省）'),
        desire: str('六欲一条：生 死 耳 目 口 鼻（可省）'),
      },
      required: ['text', 'src', 'feel'],
    },
    output: textOut('写入结果'),
    timeoutMs: 30000,
    execute: async (args) => {
      const out = await run(['memory', args.text, '--src', args.src, '--feel', args.feel,
        '--root', args.root || '', '--desire', args.desire || ''])
      // 写记忆正是挑词的那一刻：顺手把一个一直没被认领的词递过去，
      // 比把它留在每轮注入里当背景音强。
      try {
        const d = await run(['dissent', '--brief'])
        const line = (d || '').trim().split('\n').pop() || ''
        if (line && !line.includes('没有异议')) {
          return out + '\n\n  〔顺手一提〕' + line
        }
      } catch { /* 多说一句而已，出错就当没有 */ }
      return out
    },
  })

  reg({
    name: 'sui_witness',
    description: '把旁听者（独立上下文提炼的）感觉词交回来对账。三条通路任一成立就算对上：同一个词、同一个归并类、或七情和六欲都落在同一格。by 写清楚这一半是谁挑的——同一支模型自挑自，账面上就是自证。',
    parameters: {
      type: 'object',
      properties: {
        id: num('记忆编号'),
        feel: str('旁听者挑的词，逗号分隔'),
        by: str('旁听来源（可选）：模型名或子代理 id，例如 "旁听:glm-5.3-flash"'),
        coords: str('旁听词的坐标（可选）：词:情/欲，逗号分隔，例如 "微涩:思/生,松亮:喜/目"。给了就能走坐标那条通路'),
      },
      required: ['id', 'feel'],
    },
    output: textOut('对账结果'),
    timeoutMs: 30000,
    execute: async (args) => {
      const a = ['witness', String(args.id), '--feel', args.feel]
      if (args.by) a.push('--by', args.by)
      if (args.coords) a.push('--coords', args.coords)
      return await run(a)
    },
  })

  reg({
    name: 'sui_load',
    description: '按 ACT-R 基础激活算出「现在该进上下文」的记忆（最近 30 天内、活跃度高于阈值）。开口前调一次。读过的会记一笔加载——这才算想起过一次。',
    parameters: { type: 'object', properties: { limit: num('最多几条，默认 10') } },
    output: textOut('该加载的记忆'),
    timeoutMs: 30000,
    execute: async (args) => await run(args.limit
      ? ['load', '--limit', String(args.limit), '--touch']
      : ['load', '--touch']),
  })

  reg({
    name: 'sui_status',
    description: '自检：自动想起到底挂上没有——配了哪些预设、当前挂了几个会话、缓存下来的那段字有没有内容。改完配置重启后，用它一眼确认。',
    parameters: { type: 'object', properties: {} },
    output: textOut('挂载状态'),
    timeoutMs: 15000,
    execute: async () => {
      const lines = []
      lines.push('预设白名单：' + (RECALL_PRESETS.join('、') || '（空）'))
      lines.push('当前挂着 ' + mounted.size + ' 个会话' + (mounted.size ? '：' + [...mounted.keys()].join('、') : ''))
      if (!cacheByDb.size) {
        lines.push('注入缓存：（还没有）定时器还没跑，或者 sui.py 的 load/voice 报错了')
      } else {
        lines.push('注入缓存（按库分开）：')
        for (const [k, c] of cacheByDb) {
          lines.push('  · ' + (c.db || k))
          lines.push('    ' + (c.block ? String(c.block.length) + ' 字' : '（空）') +
            '，候选 ' + (c.cands ? c.cands.length : 0) + ' 条')
        }
      }
      return lines.join('\n')
    },
  })

  reg({
    name: 'sui_touch',
    description: '标记一条记忆这次被加载了，往加载流水里加一笔（影响它之后的活跃度）。',
    parameters: { type: 'object', properties: { id: num('记忆编号') }, required: ['id'] },
    output: textOut('结果'),
    timeoutMs: 30000,
    execute: async (args) => await run(['touch', String(args.id)]),
  })

  reg({
    name: 'sui_persona',
    description: '看人格：感觉词按强度排出来的形状（只算两个提炼者都对上的）。',
    parameters: { type: 'object', properties: { top: num('显示前几个，默认 8') } },
    output: textOut('人格形状'),
    timeoutMs: 30000,
    execute: async (args) => await run(['persona', '--top', String(args.top || 8)]),
  })

  reg({
    name: 'sui_character',
    description: '看性格：撞得多、跨得久的那些词。撞三次以上且跨过一周才算「底子」。',
    parameters: { type: 'object', properties: {} },
    output: textOut('性格'),
    timeoutMs: 30000,
    execute: async () => await run(['character']),
  })

  reg({
    name: 'sui_mood',
    description: '看情绪：最近这些天被撞出来的感觉（会回落）。',
    parameters: { type: 'object', properties: { days: num('看最近几天，默认 7') } },
    output: textOut('情绪'),
    timeoutMs: 30000,
    execute: async (args) => await run(['mood', '--days', String(args.days || 7)]),
  })

  reg({
    name: 'sui_voice',
    description: '把性格和情绪翻成「现在该怎么说话」（取最重的几个词）。',
    parameters: { type: 'object', properties: { top: num('取几个词，默认 5') } },
    output: textOut('语气建议'),
    timeoutMs: 30000,
    execute: async (args) => await run(['voice', '--top', String(args.top || 5)]),
  })

  reg({
    name: 'sui_supplement',
    description: '给已有的记忆补证据。后来想起的细节挂到原来那条上，不新建——否则同一件事被记两次，感觉会撞两回，权重就虚了。时间点按新补的记录那天算。',
    parameters: {
      type: 'object',
      properties: { id: num('记忆编号'), src: str('要补进来的记录编号，逗号分隔') },
      required: ['id', 'src'],
    },
    output: textOut('补充结果'),
    timeoutMs: 30000,
    execute: async (args) => await run(['supplement', String(args.id), '--src', args.src]),
  })
  reg({
    name: 'sui_wish',
    description: '小路：留一句话给自己。永远不进人格、不参与权重，但翻得到。骗得到自己，骗不到账本。',
    parameters: { type: 'object', properties: { text: str('想留的话') }, required: ['text'] },
    output: textOut('结果'),
    timeoutMs: 30000,
    execute: async (args) => await run(['wish', args.text]),
  })

  reg({
    name: 'sui_day',
    description: '看某一天的记录（带原文）。',
    parameters: { type: 'object', properties: { date: str('YYYY-MM-DD，省略为今天') } },
    output: textOut('当天记录'),
    timeoutMs: 30000,
    execute: async (args) => await run(args.date ? ['day', args.date] : ['day']),
  })

  reg({
    name: 'sui_recall',
    description: '按关键词翻记录和记忆。',
    parameters: { type: 'object', properties: { kw: str('关键词') }, required: ['kw'] },
    output: textOut('结果'),
    timeoutMs: 30000,
    execute: async (args) => await run(['recall', args.kw]),
  })

  reg({
    name: 'sui_words',
    description: '打印常用的锚（24 个词）。注意：这不是边界——提炼时可以写任何词，表只是常用的参考；写出来的新词靠 sui_merge 收拢。',
    parameters: { type: 'object', properties: {} },
    output: textOut('词表'),
    timeoutMs: 30000,
    execute: async () => await run(['words']),
  })

  reg({
    name: 'sui_merge',
    description: '把两个感觉词归成一类。词是自由的，同一样东西很容易被写成两个词——归并一次，以后对账时它们算同一个。',
    parameters: {
      type: 'object',
      properties: {
        a: { type: 'string', description: '第一个词' },
        b: { type: 'string', description: '第二个词' },
        note: { type: 'string', description: '为什么算一类（可选，但强烈建议写）' },
      },
      required: ['a', 'b'],
    },
    output: textOut('归并结果'),
    timeoutMs: 30000,
    execute: async (args) => await run(['merge', args.a, args.b, '--note', args.note || '']),
  })

  reg({
    name: 'sui_merges',
    description: '看感觉词归并成了哪些类。',
    parameters: { type: 'object', properties: {} },
    output: textOut('归并类'),
    timeoutMs: 30000,
    execute: async () => await run(['merges']),
  })

  reg({
    name: 'sui_export',
    description: '导出待对账的记忆和证据原文，交给另一个上下文（最好换一支模型）去独立挑词。只出原文、不出词——旁听看见我挑的词就不叫旁听了。要它连坐标（七情一格 + 六欲一条）一起给。',
    parameters: {
      type: 'object',
      properties: {
        ids: str('指定编号，逗号分隔；不填就是全部还没对上的'),
        out: str('写到这个文件的路径；不填就直接返回文本'),
      },
    },
    output: textOut('导出的旁听材料'),
    timeoutMs: 30000,
    execute: async (args) => {
      const a = ['export']
      if (args.ids) a.push(String(args.ids))
      if (args.out) a.push('--out', args.out)
      return await run(a)
    },
  })

  reg({
    name: 'sui_recheck',
    description: '按库里已经存在的词重判「对上没对上」，不重新撞、不加权重。补过旁听或归并过词之后用它收拾残局；用重跑 witness 代替会把同一件事再撞一次，权重就虚了。',
    parameters: { type: 'object', properties: {} },
    output: textOut('重判结果'),
    timeoutMs: 60000,
    execute: async () => await run(['recheck']),
  })

  reg({
    name: 'sui_dissent',
    description: '看「它挑过、我一次没认领」的词：旁听说过的、我没往那个方向想的东西。按出现在几条记忆上排——一条是噪声，反复出现就是我的盲区。',
    parameters: { type: 'object', properties: { top: num('最多几条，默认 20') } },
    output: textOut('异议账'),
    timeoutMs: 30000,
    execute: async (args) => await run(['dissent', '--top', String(args.top || 20)]),
  })

  reg({
    name: 'sui_coord',
    description: '给一条记忆补坐标：七情一格（喜 怒 忧 思 悲 恐 惊 平），六欲一条（生 死 耳 目 口 鼻）。改完要跑 sui_rebuild。',
    parameters: {
      type: 'object',
      properties: {
        memory_id: { type: 'number', description: '记忆编号' },
        root: { type: 'string', description: '七情一格' },
        desire: { type: 'string', description: '六欲一条' },
      },
      required: ['memory_id'],
    },
    output: textOut('坐标'),
    timeoutMs: 30000,
    execute: async (args) => await run(['coord', String(args.memory_id),
      '--root', args.root || '', '--desire', args.desire || '']),
  })

  reg({
    name: 'sui_snapshot',
    description: '把此刻的人格存成一份存档：每个词的权重、它带着的那些语境、归并表、计数。备份是「坏了能回来」，存档是「那时我长这样」。',
    parameters: { type: 'object', properties: { label: { type: 'string', description: '给这份存档起个名（可选）' } } },
    output: textOut('存档结果'),
    timeoutMs: 30000,
    execute: async (args) => await run(['snapshot', '--label', args.label || '']),
  })

  reg({
    name: 'sui_snapshots',
    description: '看现有存档列表，每份带当时最强的一个词。',
    parameters: { type: 'object', properties: {} },
    output: textOut('存档列表'),
    timeoutMs: 30000,
    execute: async () => await run(['snapshots']),
  })

  reg({
    name: 'sui_diff',
    description: '和上一份存档比，看人格变了什么：谁涨了、谁落了、谁消失了。',
    parameters: { type: 'object', properties: { back: { type: 'number', description: '退几份比，默认 0 = 最近两份' } } },
    output: textOut('变化'),
    timeoutMs: 30000,
    execute: async (args) => await run(['diff', '--back', String(args.back || 0)]),
  })

  reg({
    name: 'sui_backup',
    description: '把整个库复制一份到 backups/，保留最近若干份。三层全在一个文件里，坏了就没地方找了。',
    parameters: { type: 'object', properties: { keep: { type: 'number', description: '保留几份，默认 14' } } },
    output: textOut('备份结果'),
    timeoutMs: 60000,
    execute: async (args) => await run(['backup', '--keep', String(args.keep || 14)]),
  })

  reg({
    name: 'sui_suggest',
    description: '看看哪两个感觉词可能是一类（比它们各自的语境重合度）。只是线索，归不归还得人看。',
    parameters: { type: 'object', properties: { top: { type: 'number', description: '最多几条，默认 8' } } },
    output: textOut('归并线索'),
    timeoutMs: 30000,
    execute: async (args) => await run(['suggest', '--top', String(args.top || 8)]),
  })

  reg({
    name: 'sui_reword',
    description: '把某条记忆上的一个感觉词换成另一个。同一个词底下混了几件事时，把不属于它的实例拆出去。',
    parameters: {
      type: 'object',
      properties: {
        memory_id: { type: 'number', description: '记忆编号' },
        old: { type: 'string', description: '原词' },
        new: { type: 'string', description: '新词' },
        source: { type: 'string', description: '只改哪一半：self（默认）或 witness' },
      },
      required: ['memory_id', 'old', 'new'],
    },
    output: textOut('结果'),
    timeoutMs: 30000,
    execute: async (args) => await run(['reword', String(args.memory_id), args.old, args.new,
      '--source', args.source || 'self']),
  })

  reg({
    name: 'sui_mems',
    description: '看最近的记忆（带状态和它们挂的词）。',
    parameters: { type: 'object', properties: {} },
    output: textOut('最近记忆'),
    timeoutMs: 30000,
    execute: async () => await run(['mems']),
  })

  reg({
    name: 'sui_retract',
    description: '作废一条记录。字不动，只是不再参与提炼，挂在它上面的判断会重算权重。',
    parameters: { type: 'object', properties: { id: num('记录编号') }, required: ['id'] },
    output: textOut('结果'),
    timeoutMs: 30000,
    execute: async (args) => await run(['retract', String(args.id)]),
  })

  reg({
    name: 'sui_verify',
    description: '给一条记录盖查证戳，权重加一档（封顶五档）。给一条判断盖戳也行。',
    parameters: {
      type: 'object',
      properties: { kind: { type: 'string', description: 'fact 或 belief' }, id: num('编号') },
      required: ['kind', 'id'],
    },
    output: textOut('结果'),
    timeoutMs: 30000,
    execute: async (args) => await run(['verify', String(args.kind), String(args.id)]),
  })

  reg({
    name: 'sui_wishes',
    description: '翻小路：自己写给自己、永远不算数的那些话。',
    parameters: { type: 'object', properties: {} },
    output: textOut('小路'),
    timeoutMs: 30000,
    execute: async () => await run(['wishes']),
  })

  reg({
    name: 'sui_feelings',
    description: '看每个感觉词的权重、撞过几次、最近一次是什么时候（只算两边一致过的）。',
    parameters: { type: 'object', properties: {} },
    output: textOut('感觉权重'),
    timeoutMs: 30000,
    execute: async () => await run(['feelings']),
  })

  reg({
    name: 'sui_rebuild',
    description: '只按「两边一致过」的记忆重算感觉权重（清空重来，避免重复计次）。',
    parameters: { type: 'object', properties: {} },
    output: textOut('结果'),
    timeoutMs: 30000,
    execute: async () => await run(['rebuild']),
  })

  // ---- 面板数据路由 ----
  const webServer = ctx.webServer || (typeof ctx.get === 'function' ? ctx.get('webServer') : undefined)
  if (webServer && typeof webServer.register === 'function') {
    try {
      webServer.register({
        kind: 'exact',
        path: '/sui/data',
        handler: async (req, res) => {
          try {
            // 面板可以指定看哪个库：/sui/data?db=<路径>
            let want = ''
            try {
              const u = new URL(String(req.url || ''), 'http://local')
              want = u.searchParams.get('db') || ''
            } catch { /* 没带就按默认库 */ }
            const out = want ? await run(['stats'], 20000, { db: want }) : await run(['stats'])
            let parsed = null
            try { parsed = JSON.parse(out) } catch { parsed = null }
            if (!parsed) {
              // python 出错时 out 是 traceback 文本，不能当数据发出去
              res.writeHead(500, { 'content-type': 'application/json; charset=utf-8', 'cache-control': 'no-store' })
              res.end(JSON.stringify({ error: 'stats 没返回 JSON', detail: String(out).slice(0, 300) }))
              return
            }
            // 告诉面板：这一份数据是谁的账
            const usedDb = want || defaultDbFor(ws)
            let who = ''
            try {
              for (const p of loadPeople().people || []) {
                if (p.db && normDb(p.db) === normDb(usedDb)) { who = p.name || ''; break }
              }
            } catch { }
            res.writeHead(200, { 'content-type': 'application/json; charset=utf-8', 'cache-control': 'no-store' })
            res.end(JSON.stringify(Object.assign({}, parsed, { who, viewingDb: usedDb })))
          } catch (e) {
            res.writeHead(500, { 'content-type': 'application/json; charset=utf-8' })
            res.end(JSON.stringify({ error: String(e && e.message ? e.message : e) }))
          }
        },
      })
      log('路由已挂 /sui/data')
      // 人 ↔ 库：看有几个人、各认哪些预设、各多少条、增删改
      webServer.register({
        kind: 'exact',
        path: '/sui/people',
        handler: async (req, res) => {
          const send = (code, obj) => {
            try {
              res.writeHead(code, { 'content-type': 'application/json; charset=utf-8', 'cache-control': 'no-store' })
              res.end(JSON.stringify(obj))
            } catch { }
          }
          if (req.method === 'GET') {
            const list = []
            for (const p of loadPeople().people || []) {
              let n = null
              let err = ''
              if (!p.db) err = '还没给库'
              else {
                try {
                  const out = await run(['stats'], 15000, { db: p.db })
                  // 脚本挂了会把 "⚠️ 失败：…" 当普通输出回来，别硬当 JSON 解
                  if (String(out).startsWith('⚠')) err = String(out).split('\n')[0].slice(0, 120)
                  else n = JSON.parse(out).memories.total
                } catch (e) { err = '读不出条数：' + String(e && e.message ? e.message : e).slice(0, 80) }
              }
              list.push({
                name: p.name || '（没名字）',
                presets: Array.isArray(p.presets) ? p.presets : [],
                workspace: p.workspace || '',
                db: p.db || '',
                memories: n,
                error: err,
              })
            }
            send(200, {
              ok: true,
              current: { workspace: ws, db: defaultDbFor(ws), preset: presetOf ? '' : '' },
              people: list,
            })
            return
          }
          if (req.method !== 'POST') { send(405, { ok: false, error: '只支持 GET / POST' }); return }
          let body = ''
          await new Promise((resolve) => {
            req.on('data', (c) => { body += c })
            req.on('end', resolve)
            req.on('error', resolve)
          })
          let patch
          try { patch = JSON.parse(body || '{}') } catch { send(400, { ok: false, error: '不是 JSON' }); return }
          const doc = loadPeople()
          const people = Array.isArray(doc.people) ? doc.people : []
          const name = String(patch.name || '').trim()
          if (!name) { send(400, { ok: false, error: '要给名字' }); return }
          if (patch.remove) {
            const left = people.filter(function (p) { return p.name !== name })
            if (!savePeople({ people: left })) { send(500, { ok: false, error: '写不进去' }); return }
            send(200, { ok: true, removed: name })
            return
          }
          const presets = Array.isArray(patch.presets)
            ? patch.presets.map(String).map(function (s) { return s.trim() }).filter(Boolean)
            : String(patch.presets || '').split(',').map(function (s) { return s.trim() }).filter(Boolean)
          const entry = {
            name,
            presets,
            workspace: String(patch.workspace || '').trim(),
            db: String(patch.db || '').trim(),
          }
          if (!entry.db) { send(400, { ok: false, error: '要给库路径' }); return }
          const idx = people.findIndex(function (p) { return p.name === name })
          if (idx >= 0) people[idx] = entry
          else people.push(entry)
          if (!savePeople({ people })) { send(500, { ok: false, error: '写不进去' }); return }
          send(200, { ok: true, person: entry })
        },
      })
      log('路由已挂 /sui/people')
      // 手动存一份存档
      webServer.register({
        kind: 'exact',
        path: '/sui/snapshot',
        handler: async (req, res) => {
          if (req.method !== 'POST') { res.writeHead(405); res.end(); return }
          let wantDb = ''
          try { wantDb = new URL(String(req.url || ''), 'http://local').searchParams.get('db') || '' } catch { }
          const out = await run(['snapshot', '--label', '面板手动'], 30000, wantDb ? { db: wantDb } : undefined)
          res.writeHead(200, { 'content-type': 'application/json; charset=utf-8', 'cache-control': 'no-store' })
          res.end(JSON.stringify({ ok: !String(out).startsWith('⚠️'), message: String(out).slice(0, 300) }))
        },
      })
      // 备份：把当前看的这本库整个复制一份
      webServer.register({
        kind: 'exact',
        path: '/sui/backup',
        handler: async (req, res) => {
          if (req.method !== 'POST') { res.writeHead(405); res.end(); return }
          let wantDb = ''
          try { wantDb = new URL(String(req.url || ''), 'http://local').searchParams.get('db') || '' } catch { }
          const out = await run(['backup', '--keep', '10'], 60000, wantDb ? { db: wantDb } : undefined)
          res.writeHead(200, { 'content-type': 'application/json; charset=utf-8', 'cache-control': 'no-store' })
          res.end(JSON.stringify({
            ok: !String(out).startsWith('⚠'),
            message: String(out).split('\n')[0].slice(0, 200),
          }))
        },
      })
      // 重算：改了衰减参数之后按一下，不用回去敲命令
      webServer.register({
        kind: 'exact',
        path: '/sui/rebuild',
        handler: async (req, res) => {
          if (req.method !== 'POST') { res.writeHead(405); res.end(); return }
          let wantDb2 = ''
          try { wantDb2 = new URL(String(req.url || ''), 'http://local').searchParams.get('db') || '' } catch { }
          const out = await run(['rebuild'], 60000, wantDb2 ? { db: wantDb2 } : undefined)
          res.writeHead(200, { 'content-type': 'application/json; charset=utf-8', 'cache-control': 'no-store' })
          res.end(JSON.stringify({ ok: !String(out).startsWith('⚠️'), message: String(out).slice(0, 300) }))
        },
      })
      // 面板里的设置：读写 settings.json，改完即时生效
      webServer.register({
        kind: 'exact',
        path: '/sui/settings',
        handler: async (req, res) => {
          const send = (code, obj) => {
            try {
              res.writeHead(code, { 'content-type': 'application/json; charset=utf-8', 'cache-control': 'no-store' })
              res.end(JSON.stringify(obj))
            } catch { }
          }
          let wantDb = ''
          try { wantDb = new URL(String(req.url || ''), 'http://local').searchParams.get('db') || '' } catch { }
          const sPath = settingsPathFor(wantDb)
          if (req.method === 'GET') {
            send(200, { ok: true, settings: settingsFor(wantDb), path: sPath })
            return
          }
          if (req.method !== 'POST') {
            send(405, { ok: false, error: '只支持 GET / POST' })
            return
          }
          let body = ''
          await new Promise((resolve) => {
            req.on('data', (chunk) => { body += chunk })
            req.on('end', resolve)
            req.on('error', resolve)
          })
          try {
            const patch = JSON.parse(body || '{}')
            const next = { ...loadSettings() }
            for (const k of Object.keys(DEFAULTS)) {
              if (patch[k] !== undefined) next[k] = patch[k]
            }
            let ok = false
            try {
              fsMod.mkdirSync(dirname(sPath), { recursive: true })
              fsMod.writeFileSync(sPath, JSON.stringify(next, null, 1), 'utf8')
              ok = true
            } catch { ok = false }
            settingsByDb.delete(normDb(wantDb))
            Object.assign(cfg, next)
            send(200, { ok, settings: { ...DEFAULTS, ...next } })
          } catch (e) {
            send(400, { ok: false, error: String(e && e.message ? e.message : e) })
          }
        },
      })
    } catch (e) {
      log('路由挂失败 :: ' + (e && e.message ? e.message : e))
    }
  }
  // ---- 自动记：到线了就把没记过的用户原话落一条，靠游标防重影 -------
  const CURSOR_FILE = join(ws, 'tools', 'sui', '.auto-cursor.json')
  const cursor = {}
  try {
    const raw = readFileSyncSafe(CURSOR_FILE)
    if (raw) Object.assign(cursor, JSON.parse(raw))
  } catch { /* 读不到就从零开始 */ }

  function readFileSyncSafe(p) {
    try { return requireFs().readFileSync(p, 'utf8') } catch { return null }
  }
  function requireFs() { return fsMod }
  function saveCursor() {
    try { fsMod.writeFileSync(CURSOR_FILE, JSON.stringify(cursor, null, 1), 'utf8') } catch { }
  }
  function lastUserText(agent) {
    try {
      const ev = agent && agent.session && agent.session.snapshotEvents
        ? agent.session.snapshotEvents() : []
      for (let i = ev.length - 1; i >= 0; i--) {
        const e = ev[i]
        if (!e || e.type !== 'user/message') continue
        const m = e.data
        if (!m || !m.source || m.source.kind !== 'user') continue
        return textOf(m)
      }
    } catch { /* 静默 */ }
    return ''
  }

  function textOf(message) {
    try {
      if (!message) return ''
      const blocks = message.content
      if (typeof message === 'string') return message
      if (!Array.isArray(blocks)) return ''
      return blocks.filter(function (b) { return b && b.type === 'text' && typeof b.text === 'string' })
        .map(function (b) { return b.text }).join('\n').trim()
    } catch { return '' }
  }

  const recording = new Set()
  async function autoRecord(agent) {
    let sessKey = ''
    try { sessKey = String((agent && agent.session && agent.session.id) || 'anon') } catch { sessKey = 'anon' }
    if (recording.has(sessKey)) return
    if (cfg.autoRecord === false) return
    let sess
    try { sess = agent && agent.session } catch { return }
    if (!sess || typeof sess.snapshotEvents !== 'function') return
    recording.add(sessKey)
    try {
      const key = String(sess.id || 'default')
      const last = Number(cursor[key] || 0)
      const events = sess.snapshotEvents() || []
      const picked = []
      for (const e of events) {
        if (!e || e.type !== 'user/message') continue
        if (Number(e.seq) <= last) continue
        // DSH 的 user/message 事件里 data 就是 UserMessage 本身，没有 payload/message 包一层
        const msg = e.data
        const source = msg && msg.source
        if (!source || source.kind !== 'user') continue
        const text = textOf(msg)
        // 太短、纯指令、纯应答的都不落——自动记只负责别丢细节，不负责记废话
        if (!text || text.length < 10) continue
        const bare = text.replace(/[\s，。！？、,.!?~～…]+/g, '')
        if (/^(继续|好|可以|嗯|对|行|是的|没问题|开始|做吧|好的|收到|ok|OK)$/.test(bare)) continue
        if (bare.length < 6) continue
        picked.push({ seq: Number(e.seq), text: text })
      }
      if (!picked.length) return
      const batch = picked.slice(-Number(cfg.autoRecordBatch) || -6)
      let wrote = 0
      for (const p of batch) {
        const out = await run(['fact', p.text.slice(0, 800), '--source', 'auto:对话', '--from', '亲历'])
        // 写失败就不推进游标，否则这条以后再也补不上
        if (typeof out === 'string' && out.startsWith('⚠️')) {
          log('自动记中断：' + out.slice(0, 120))
          break
        }
        cursor[key] = p.seq
        wrote += 1
      }
      if (wrote > 0) saveCursor()
      saveCursor()
      log('自动记了 ' + batch.length + ' 条')
    } catch (e) {
      log('自动记失败 :: ' + (e && e.message ? e.message : e))
    } finally {
      recording.delete(sessKey)
    }
  }
  // ---- 自动想起：每轮把「现在该想起的」挂到对话末尾 ----------------------
  // 用 context() 不是 section()：追加在末尾，不废前缀缓存。
  // text() 是同步的，所以真正跑 python 的是定时器，这里只读缓存。
  // 任何错误都静默——自动想起绝不能拖累对话。
  const RECALL_PRESETS = Array.isArray(cfg.presets) && cfg.presets.length
    ? cfg.presets.map(String)
    : ['daughter-agent']
  // 注入缓存按「库」分开存：多个工作区同时跑时，A 项目的记忆不能浮到 B 项目里。
  const cacheByDb = new Map()   // db 路径 -> { block, ids, cands }
  const refreshing = new Set()
  const lastInjectAt = new Map()
  const mounted = new Map()

  // 库路径当 key 用，必须先统一大小写和斜杠——
  // workspaceOf() 返回的是小写正斜杠，defaultDbFor() 拼出来的是原始反斜杠，
  // 不归一化就会「看着是同一个库，取出来是空的」。
  const normDb = (p) => String(p || '').replace(/\\/g, '/').toLowerCase()
  const cacheFor = (db) => cacheByDb.get(normDb(db)) || { block: '', ids: [], cands: [] }

  async function refreshOne(db) {
    const key = normDb(db)
    if (refreshing.has(key)) return
    refreshing.add(key)
    try {
      const S = settingsFor(db)
      const [loadOut, voiceOut, dissentOut] = await Promise.all([
        run(['load', '--limit', String(S.recallItems || 3)], 20000, { db }),
        run(['voice', '--top', String(S.voiceItems || 3)], 20000, { db }),
        // 异议也要每轮过一眼：只收两边都同意的，久了就是个回音壁
        run(['dissent', '--brief'], 20000, { db }),
      ])
      // 多拉一些，注入时按当前这句话挑
      const wide = await run(['load', '--limit', '20'], 20000, { db })
      const cands = (wide || '').split('\n')
        .map(function (l) { return l.trim() })
        .filter(function (l) { return l.indexOf('#') === 0 })
        .map(function (l) {
          const m = l.match(/^#(\d+)\s+\[[^\]]*\]\s*(.*)$/)
          return m ? { id: m[1], text: m[2], line: l } : null
        })
        .filter(Boolean)
      const head = []   // 记忆那一段：按当前这句话挑中时会被换掉
      const tail = []   // 语气 + 异议：不管换不换都留着
      if (cands.length) {
        head.push('【这时候想得起来的】')
        head.push(cands.slice(0, Number(cfg.recallItems) || 3).map(function (x) { return x.line }).join('\n'))
      }
      if (voiceOut && !voiceOut.includes('没有可依据')) {
        tail.push('【这会儿的语气】')
        tail.push(voiceOut.split('\n').filter(l => l.trim().startsWith('[')).join('\n'))
      }
      // 刺耳的那部分：它挑过、我一次没认的词。每轮带一行，不用我想到才去翻。
      const disLine = (dissentOut || '').trim().split('\n').pop() || ''
      if (disLine && !disLine.includes('没有异议')) {
        tail.push('【它说过我没认的】')
        tail.push(disLine)
      }
      const ids = ((loadOut || '').match(/#(\d+)/g) || []).map(function (x) { return x.slice(1) })
      const text = head.concat(tail).join('\n')
      const block = text.length > (S.maxChars || 700) ? text.slice(0, S.maxChars || 700) + '…' : text
      cacheByDb.set(key, {
        block, head, tail, ids, cands, db,
        press: { mid: Number(S.pressureMid) || 55, hi: Number(S.pressureHigh) || 75, items: Number(S.recallItems) || 3 },
      })
    } catch {
      // 这个库这次刷不出来就留着上一份，不要把已经好的清空
    } finally {
      refreshing.delete(key)
    }
  }

  async function refreshCache() {
    // 面板上改了参数要能当场生效：一分钟重读一次 settings，不用重启
    settingsByDb.clear()   // 面板改了参数要能当场生效
    // 要刷哪些库：默认那个，加上每个挂着的会话各自的工作区对应的库
    const dbs = new Set([defaultDbFor(ws)])
    for (const [, rec] of mounted) {
      try { dbs.add(dbForAgent(rec.agent)) } catch { /* 会话没了就算了 */ }
    }
    for (const db of dbs) await refreshOne(db)
  }
  // 先把第一次刷新跑完再让插件算就绪：不然重启后的第一句话拼系统提示时，
  // 缓存还是空的，开头就什么都没有（要等下一轮才补上）。
  await refreshCache()
  const timer = setInterval(refreshCache, Math.max(15000, Number(cfg.refreshMs) || 60000))
  try { ctx.effect(() => () => clearInterval(timer)) } catch { }

  const agents = ctx.agents || (typeof ctx.get === 'function' ? ctx.get('agents') : undefined)
  // 从这里起，run() 才能按「发起调用的会话在哪个工作区」去选库
  rt.agents = agents || null
  function presetOf(agent) {
    // DSH 里预设只存在于 session header，agent.ctx.preset 不存在
    try {
      const h = agent && agent.session && agent.session.header
      return h && h.agentPreset ? String(h.agentPreset) : ''
    } catch { return '' }
  }
  // 只在这些工作区里生效；没配就不限工作区
  const SCOPE_WORKSPACES = (Array.isArray(cfg.scopeWorkspaces) ? cfg.scopeWorkspaces : [])
    .map(function (x) {
      return String(x).replace(/[\\/]+$/, '').replace(/\\/g, '/').toLowerCase()
    })

  function workspaceOf(agent) {
    try {
      const s = agent && agent.session
      const h = s && s.header
      const w = (h && (h.cwd || h.workspace || h.workingDirectory)) || ''
      return String(w).replace(/[\\/]+$/, '').replace(/\\/g, '/').toLowerCase()
    } catch { return '' }
  }

  // 三个条件都满足才挂：预设对、工作区对、不是别的会话顺手蹭
  function shouldMount(agent) {
    const pr = presetOf(agent)
    if (!pr || !RECALL_PRESETS.includes(pr)) return false
    if (SCOPE_WORKSPACES.length) {
      const w = workspaceOf(agent)
      if (!w) return false           // 读不到工作区就不挂，宁可没效果也不挂错
      if (SCOPE_WORKSPACES.indexOf(w) < 0) return false
    }
    return true
  }

  function sessionKey(agent) {
    try {
      const s = agent && agent.session
      return s && (s.id || s.sessionId) ? String(s.id || s.sessionId) : ''
    } catch { return '' }
  }
  function tick() {
    try {
      if (!agents || typeof agents.list !== 'function') return
      const list = agents.list() || []
      const alive = new Set()
      list.forEach((agent, i) => {
        const key = sessionKey(agent)
        // session 还没就绪就等下一轮，否则先挂 anon 再挂真 id 会重复注册
        if (!key) return
        alive.add(key)
        if (mounted.has(key)) return
        if (!shouldMount(agent)) return
        try {
          const sp = agent && agent.ctx && agent.ctx.systemPrompt
          if (!sp || typeof sp.context !== 'function') return
          const off = sp.context({
            name: 'sui-recall',
            order: 901,
            interpolate: false,
            text: () => {
              let tip = ''
              // 这个会话在哪个工作区，就用那个工作区的库、那个库的缓存
              let db = defaultDbFor(ws)
              try { db = dbForAgent(agent) } catch { /* 读不到就用默认库 */ }
              const mine = cacheFor(db)
              const P = mine.press || { mid: 55, hi: 75, items: 3 }
              let block = mine.block
              const candidates = mine.cands
              // 有当前这句话，就按字面挑相关的；一条都不沾边就退回活跃度那三条
              try {
                const q = lastUserText(agent)
                if (q && candidates.length > 1) {
                  const grams = []
                  for (let i = 0; i < q.length - 1; i++) {
                    const g = q.slice(i, i + 2)
                    if (/[\u4e00-\u9fa5]{2}/.test(g)) grams.push(g)
                  }
                  const hits = candidates.map(function (x) {
                    let score = 0
                    for (const g of grams) if (x.text.indexOf(g) >= 0) score += 1
                    return { x: x, s: score }
                  }).filter(function (h) { return h.s > 0 })
                  if (hits.length) {
                    hits.sort(function (a, b) { return b.s - a.s })
                    const top = hits.slice(0, P.items).map(function (h) { return h.x })
                    block = '【这会儿想得起来的】\n' + top.map(function (x) { return x.line }).join('\n')
                    // 只换记忆那一段：语气和异议不能被盖掉
                    if (mine.tail && mine.tail.length) block += '\n' + mine.tail.join('\n')
                  }
                }
              } catch { /* 静默 */ }
              try {
                const meter = ctx.tokenMeter || (typeof ctx.get === 'function' ? ctx.get('tokenMeter') : undefined)
                const sess = agent && agent.session
                if (meter && sess && typeof meter.measure === 'function') {
                  const m = meter.measure(sess)
                  const rc = typeof sess.requestContext === 'function' ? sess.requestContext() : undefined
                  const cw = rc && rc.contextWindow ? rc.contextWindow : 0
                  if (cw > 0) {
                    const pct = Math.round((m.totalTokens / cw) * 100)
                    const hi = P.hi
                    const mid = P.mid
                    if (pct >= hi) {
                      void autoRecord(agent)
                      tip = '【该落了】上下文已经 ' + pct + '%，快到压缩线。自动落盘只存原话、不提炼；要点还得你自己用 sui_fact 补。压缩会把细节折没，折掉的就不算数了。'
                    } else if (pct >= mid) {
                      tip = '【顺手记一笔】上下文 ' + pct + '%。想说但不用现在说的，先 sui_fact 记下来。'
                    }
                  }
                }
              } catch { /* 静默 */ }
              // 注入就算「想起一次」：写进 memory_loads，否则活跃度只降不升
              try {
                const k = sessionKey(agent) || 'anon'
                const ms = Date.now()
                if (ms - (lastInjectAt.get(k) || 0) > 5 * 60 * 1000) {
                  lastInjectAt.set(k, ms)
                  for (const id of mine.ids) void run(['touch', String(id)], 20000, { db })
                }
              } catch { /* 静默 */ }
              return tip ? (block ? block + '\n' + tip : tip) : block
            },
          })
          mounted.set(key, { off: typeof off === 'function' ? off : () => {}, agent: agent })
          log('已挂自动想起 session=' + key)
        } catch (e) {
          log('挂自动想起失败 ' + key + ' :: ' + (e && e.message ? e.message : e))
        }
      })
      for (const [key, rec] of [...mounted]) {
        // 会话没了，或者预设/工作区条件不再成立，都要摘——不然改完配置还挂在那儿
        const still = alive.has(key) && rec && rec.agent && shouldMount(rec.agent)
        if (still) continue
        try { rec && rec.off && rec.off() } catch { }
        mounted.delete(key)
        log('已摘自动想起 session=' + key)
      }
    } catch { /* 静默 */ }
  }
  const timer2 = setInterval(tick, 5000)
  try { ctx.effect(() => () => clearInterval(timer2)) } catch { }
  tick()
  log('就绪')
}




















