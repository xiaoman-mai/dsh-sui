#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
sui — 三层：记录 / 记忆 / 感觉（双提炼版）

  记录 fact     什么都可以记，像日记。带日期、出处、原文。不进上下文，只给工具。
  记忆 memory    只能从记录里提炼。带活跃度，最近一个月内按活跃度主动加载。
  感觉 feeling   提炼记忆时带出来的词。**必须两个提炼者都挑中才算数。**

为什么要两个提炼者：
  一个人挑词，想美化就在那一步动手，系统看不出来。所以同一段记录提炼两次——
  一次是我，一次是不知道我挑了什么的旁听者。两边都挑中的词才进人格；
  只有一边挑中的，记忆标「有分歧」，词不进去，但留着给人看。

小路 wish：
  留一行给自己。写「我希望这件事是 X」，进另一张表，
  永远不进人格、不进权重。骗得到自己，骗不到账本。

其余规矩：
  1. 记录只追加，作废翻标记，不改字。原文（quote）留着。
  2. 记忆必须挂记录、必须带词表里的词。没有记录不许提炼。
  3. 感觉的词只能从固定词表里挑。
  4. 活跃度 = (1 + 加载次数) × exp(-Δ天 / S)，S 随加载次数变大。低于阈值就不主动加载。
"""
import sqlite3, sys, os, argparse, math, json, shutil, random
from datetime import datetime, timedelta

try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

HERE = os.path.dirname(os.path.abspath(__file__))
DB = os.environ.get('SUI_DB') or os.environ.get('M3_DB') or os.path.join(HERE, 'sui.db')

# 七情（《黄帝内经》）：喜 怒 忧 思 悲 恐 惊，各连一脏。
# 另加一格「平」——安、静、稳这些不是七情，是没被情牵动的状态。
QIQING = ['喜', '怒', '忧', '思', '悲', '恐', '惊', '平']
# 六欲（《吕氏春秋》及高诱注）：生、死、耳、目、口、鼻。
# 七情是状态，六欲是方向——可以同时成立。
DESIRES = ['生', '死', '耳', '目', '口', '鼻']

ZHANG = {'喜': '心', '怒': '肝', '忧': '肺', '思': '脾', '悲': '肺', '恐': '肾', '惊': '肾', '平': '—'}

WORDS = [
    '安', '暖', '亮', '畅', '满', '稳', '静', '软',
    '急', '慌', '闷', '沉', '空', '钝', '累', '烦',
    '羞', '怯', '疚', '怒', '硬', '奇', '念', '远',
]

LEVELS = {'感觉': 1, '推断': 2, '转述': 3, '亲历': 4, '查证': 5}
LEVEL_NAMES = {v: k for k, v in LEVELS.items()}

# 语气：一个词一句「现在该怎么说话」。只此一份。
# 以前注入用一份、命令行用一份，同一个「满」在两处说反了话（2026-11-06 合）。
TONE = {
    '暖': '可以多一句关心，但别腻',
    '满': '少炫耀，把东西放下就走',
    '稳': '别绕，直说',
    '亮': '可以带一点兴致，但别吵',
    '通': '说透，别停在半路',
    '软': '话别硬，留余地',
    '安': '语气可以平，不用起伏',
    '静': '留白比填满好',
    '急': '句子再短一截，别铺垫',
    '慌': '先说结论，再说为什么',
    '闷': '少解释，允许停住',
    '沉': '慢一点，多用具体的例子',
    '空': '别硬找话说，没话说就不说',
    '钝': '别急着表态，说不清就说不清',
    '累': '不铺陈，能一句说完就不说两句',
    '烦': '别接太长的话',
    '怕': '小心一点，别碰硬的',
    '硬': '该说死的说死',
    '怒': '不还嘴，先放着',
    '羞': '不解释，跳过',
    '怯': '不合影，也不逞强',
    '疚': '认了就改，别反复道歉',
    '念': '先说在意的，再说别的',
    '远': '不硬拉近，保持距离',
    '畅': '顺着说，不用绕回去补',
    '奇': '可以多问一句',
}
TONE_FALLBACK = '顺着这个词的调子说'

# ---- 可调参数：优先读 settings.json（面板里改的就是它）----
def _load_settings():
    p = os.path.join(HERE, 'settings.json')
    try:
        with open(p, 'r', encoding='utf-8') as f:
            j = json.load(f)
        return j if isinstance(j, dict) else {}
    except Exception:
        return {}

_CFG = _load_settings()
DECAY_POWER = float(_CFG.get('decayPower', 0.5))      # ACT-R 的 d
DECAY_THRESHOLD = float(_CFG.get('decayThreshold', 0.2))
LOAD_WINDOW_DAYS = int(_CFG.get('loadWindowDays', 30))

SCHEMA = """
CREATE TABLE IF NOT EXISTS facts (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts TEXT NOT NULL,
  day TEXT NOT NULL,
  text TEXT NOT NULL,
  quote TEXT,
  source TEXT,
  weight INTEGER NOT NULL DEFAULT 2,
  verified INTEGER NOT NULL DEFAULT 0,
  retracted INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS memories (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  text TEXT NOT NULL,
  created TEXT NOT NULL,
  last_loaded TEXT,
  load_count INTEGER NOT NULL DEFAULT 0,
  state TEXT NOT NULL DEFAULT 'pending'
);
CREATE TABLE IF NOT EXISTS memory_facts (
  memory_id INTEGER NOT NULL,
  fact_id INTEGER NOT NULL,
  PRIMARY KEY (memory_id, fact_id)
);
CREATE TABLE IF NOT EXISTS feelings (
  keyword TEXT PRIMARY KEY,
  weight REAL NOT NULL DEFAULT 0,
  hits INTEGER NOT NULL DEFAULT 1,
  first_at TEXT,
  last_at TEXT
);
CREATE TABLE IF NOT EXISTS memory_feelings (
  memory_id INTEGER NOT NULL,
  keyword TEXT NOT NULL,
  source TEXT NOT NULL DEFAULT 'self',
  context TEXT,
  kind TEXT,
  root TEXT,
  desire TEXT,
  PRIMARY KEY (memory_id, keyword, source)
);
CREATE TABLE IF NOT EXISTS wishes (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts TEXT NOT NULL,
  text TEXT NOT NULL,
  memory_id INTEGER
);
CREATE TABLE IF NOT EXISTS feeling_hits (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  keyword TEXT NOT NULL,
  memory_id INTEGER,
  ts TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS memory_loads (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  memory_id INTEGER NOT NULL,
  ts TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_hits_keyword ON feeling_hits(keyword, ts);
CREATE INDEX IF NOT EXISTS idx_hits_memory ON feeling_hits(memory_id);
CREATE INDEX IF NOT EXISTS idx_loads_memory ON memory_loads(memory_id);
CREATE INDEX IF NOT EXISTS idx_facts_day ON facts(day);
CREATE TABLE IF NOT EXISTS merges (
  a TEXT NOT NULL,
  b TEXT NOT NULL,
  note TEXT,
  created TEXT,
  PRIMARY KEY (a, b)
);
"""


def conn():
    c = sqlite3.connect(DB, timeout=10.0)
    c.row_factory = sqlite3.Row
    try:
        c.execute('PRAGMA journal_mode=WAL')
        c.execute('PRAGMA busy_timeout=8000')
        c.execute('PRAGMA synchronous=NORMAL')
    except Exception:
        pass
    c.executescript(SCHEMA)
    cols = {r[1] for r in c.execute('PRAGMA table_info(facts)')}
    if 'weight' not in cols:
        c.execute('ALTER TABLE facts ADD COLUMN weight INTEGER NOT NULL DEFAULT 2')
    if 'verified' not in cols:
        c.execute('ALTER TABLE facts ADD COLUMN verified INTEGER NOT NULL DEFAULT 0')
    if 'quote' not in cols:
        c.execute('ALTER TABLE facts ADD COLUMN quote TEXT')
    if 'owner' not in cols:
        # 一个库里可能混着两个人的记录。owner 记是谁的事，默认是自己。
        c.execute("ALTER TABLE facts ADD COLUMN owner TEXT NOT NULL DEFAULT 'me'")
    cols = {r[1] for r in c.execute('PRAGMA table_info(memories)')}
    if 'state' not in cols:
        c.execute("ALTER TABLE memories ADD COLUMN state TEXT NOT NULL DEFAULT 'pending'")
    if 'witness_by' not in cols:
        c.execute('ALTER TABLE memories ADD COLUMN witness_by TEXT')
    if 'kind' not in cols:
        # 类别：人设 / 性格 / 约定 / 关系 / 技术 / 事实 / 感觉。写入时按模板自动打标。
        c.execute('ALTER TABLE memories ADD COLUMN kind TEXT')
    if 'importance' not in cols:
        # 重要度 1-5。人设类钉在 5，沉不下去；其余的按类别给底分，可以被手动改。
        c.execute('ALTER TABLE memories ADD COLUMN importance INTEGER NOT NULL DEFAULT 3')
    cols = {r[1] for r in c.execute('PRAGMA table_info(memory_feelings)')}
    if 'source' not in cols:
        c.execute("ALTER TABLE memory_feelings ADD COLUMN source TEXT NOT NULL DEFAULT 'self'")
    if 'context' not in cols:
        c.execute('ALTER TABLE memory_feelings ADD COLUMN context TEXT')
    if 'kind' not in cols:
        c.execute('ALTER TABLE memory_feelings ADD COLUMN kind TEXT')
    fcols = {r[1] for r in c.execute('PRAGMA table_info(feelings)')}
    if 'kind' not in fcols:
        c.execute('ALTER TABLE feelings ADD COLUMN kind TEXT')
    if 'root' not in fcols:
        c.execute('ALTER TABLE feelings ADD COLUMN root TEXT')
    mcols = {r[1] for r in c.execute('PRAGMA table_info(memory_feelings)')}
    if 'root' not in mcols:
        c.execute('ALTER TABLE memory_feelings ADD COLUMN root TEXT')
    if 'desire' not in mcols:
        c.execute('ALTER TABLE memory_feelings ADD COLUMN desire TEXT')
    if 'desire' not in fcols:
        c.execute('ALTER TABLE feelings ADD COLUMN desire TEXT')
    # 老库的主键是 (memory_id, keyword)，同一个词两个人各写一次会撞车。重建一次。
    ddl = c.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='memory_feelings'").fetchone()
    if ddl and 'PRIMARY KEY (memory_id, keyword, source)' not in ddl[0]:
        c.execute('ALTER TABLE memory_feelings RENAME TO mf_old')
        c.execute('''CREATE TABLE memory_feelings (
            memory_id INTEGER NOT NULL,
            keyword TEXT NOT NULL,
            source TEXT NOT NULL DEFAULT 'self',
            PRIMARY KEY (memory_id, keyword, source)
        )''')
        c.execute('INSERT OR IGNORE INTO memory_feelings (memory_id, keyword, source) SELECT memory_id, keyword, source FROM mf_old')
        c.execute('DROP TABLE mf_old')
    return c


def now():
    return datetime.now().strftime('%Y-%m-%d %H:%M')


def today():
    return datetime.now().strftime('%Y-%m-%d')


def parse_dt(s):
    for f in ('%Y-%m-%d %H:%M', '%Y-%m-%d'):
        try:
            return datetime.strptime(s, f)
        except Exception:
            pass
    return datetime.now()


def days_since(s):
    return (datetime.now() - parse_dt(s)).total_seconds() / 86400.0


def activity(m, c=None):
    """ACT-R 的基础激活：B = Σ t^-d，d 取标准值 0.5（Anderson, ACT-R 手册）。
    每次被加载算一项。加载得多的项多，久不加载的项小。
    传连接进来就复用——否则每条记忆都要新开一次库、重建一遍表结构。"""
    own = c is None
    if own:
        c = conn()
    rows = c.execute('SELECT ts FROM memory_loads WHERE memory_id=?', (m['id'],)).fetchall()
    if not rows:
        rows = [(m['created'],)]
    total = 0.0
    for (ts,) in rows:
        age = days_since(ts)
        if age < -0.02:
            continue  # 未来的时间点是假的，不参与计算
        age = max(0.0, age)
        total += (age + 0.5) ** (-DECAY_POWER)
    return total


def cluster_of(c):
    """merges 是一堆「这两个是一回事」。用并查集摊平，返回 find(词) -> 代表词。
    归并是人的判断，代码只负责让同一个类的词能互相撞上。"""
    parent = {}

    def find(x):
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for a, b in c.execute('SELECT a, b FROM merges'):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb
    return lambda x: find(x)


def parse_feels(s):
    """解析感觉词，允许带「情/欲」标记：暖:q 或 安:y。
    七情（喜 怒 哀 惧 爱 恶 欲）是情；安的静、想动的劲，挂在欲那边。
    不带标记就是未定，不硬塞。"""
    mark = {'q': 'q', 'qing': 'q', '情': 'q', 'y': 'y', 'yu': 'y', '欲': 'y'}
    out = []
    for x in s.replace('，', ',').replace(' ', ',').split(','):
        x = x.strip()
        if not x:
            continue
        w, k = x, ''
        for sep in (':', '：', '/'):
            if sep in x:
                a, b = x.rsplit(sep, 1)
                if b.strip().lower() in mark:
                    w, k = a.strip(), mark[b.strip().lower()]
                break
        if w:
            out.append((w, k))
    return out


def lv(s):
    if s in LEVELS:
        return LEVELS[s]
    if str(s).isdigit() and 1 <= int(s) <= 5:
        return int(s)
    sys.exit(f'不认识的可信度：{s}（可选：感觉/推断/转述/亲历/查证，或 1-5）')


def parse_words(s, strict=False):
    """感觉词不再限定在那 24 个字里。
    Barrett 2006：情绪概念是一组「情境化的概念化」，每次用都是重造的。
    表里的词只是常用的锚，不认识的词照收，只在 strict 时提示。"""
    ws = [x.strip() for x in s.replace('，', ',').replace(' ', ',').split(',') if x.strip()]
    if strict:
        bad = [w for w in ws if w not in WORDS]
        if bad:
            print(f'提示：{bad} 不在常用表里，照收（表只是锚，不是边界）。')
    return ws


# ---------- 记录层 ----------

def cmd_fact(a):
    c = conn()
    w = lv(a.level)
    if a.date:
        # 补记历史：给了日期就没有时刻可言，只写 00:00，别假装知道几点
        day = a.date[:10]
        ts = a.date if len(a.date) > 10 else f'{day} 00:00'
    else:
        # 当天记的，用真实时刻。以前这里也写成 00:00，等于把一天压成一个点。
        day = today()
        ts = now()
    who = (getattr(a, 'who', None) or 'me').strip() or 'me'
    cur = c.execute(
        'INSERT INTO facts (ts, day, text, quote, source, weight, owner) VALUES (?,?,?,?,?,?,?)',
        (ts, day, a.text, a.quote, a.source, w, who))
    c.commit()
    q = f'  ｜原文：{a.quote[:40]}…' if a.quote and len(a.quote) > 40 else (f'  ｜原文：{a.quote}' if a.quote else '')
    who_tag = '' if who == 'me' else f'  〔{who}〕'
    print(f"记录 #{cur.lastrowid}  [{LEVEL_NAMES[w]}]  {a.text}{q}{who_tag}")
    if not a.quote:
        # 转述却没存原话，就是以后回查时落空的那一批（2026-11-07 数出来占四成）。
        # 当场提一句，比事后想补便宜得多。
        marks = ('说', '告诉', '讲', '问', '答', '回', '称', '留言', '评论')
        if any(m in a.text for m in marks):
            print('  〔没存原话〕这条听着像转述。以后要拿它替谁说话，回查只能回到我这句概括；带上 quote 能省这一层。')


def cmd_day(a):
    c = conn()
    d = a.date or today()
    print(f'—— {d} ——')
    rows = c.execute('SELECT * FROM facts WHERE day=? ORDER BY id', (d,)).fetchall()
    if not rows:
        print('  （空）')
    for r in rows:
        flag = ' [作废]' if r['retracted'] else ''
        src = f'  （{r["source"]}）' if r['source'] else ''
        print(f'  {r["ts"][11:]}  #{r["id"]}  [{LEVEL_NAMES.get(r["weight"], r["weight"])}]  {r["text"]}{src}{flag}')
        if r['quote']:
            print(f'          ｜{r["quote"]}')


def cmd_show(a):
    """给旁听者看的：只输出记录本身，不带我的判断"""
    c = conn()
    ids = [int(x) for x in a.ids.replace('，', ',').split(',') if x.strip()]
    for i in ids:
        r = c.execute('SELECT * FROM facts WHERE id=?', (i,)).fetchone()
        if not r:
            print(f'（没有 #{i}）')
            continue
        print(f"[{i}] {r['text']}")
        if r['quote']:
            print(f"    原文：{r['quote']}")


def _fact_source_block(c, fid):
    """把一条记录摊成「我记的 / 抄本 / 可核的源」。不存在返回 False。

    抄本和源是两回事（小绒 2026-11-06 在 rice-bowl#173 指出的）：
    回查如果只回到我自己的笔记，只会越查越对——笔记不会反驳我。
    所以这里把「源」单独列出来，源到不了的时候明说。
    """
    r = c.execute('SELECT * FROM facts WHERE id=?', (fid,)).fetchone()
    if not r:
        return False
    flag = '  [作废]' if r['retracted'] else ''
    print(f"  [{r['id']}] {r['day']}  {LEVEL_NAMES.get(r['weight'], r['weight'])}{flag}")
    print(f"        我记的：{r['text']}")
    if r['quote']:
        print(f"        抄  本：{r['quote']}")
    else:
        print("        抄  本：（没存原话——这条只有我的概括，不能当依据）")
    if r['source']:
        print(f"        可核的源：{r['source']}")
    else:
        print("        可核的源：（没写——这条回不去了，别当依据）")
    return True


def cmd_quote(a):
    """开口前回查：把一条记忆（或一条记录）挂的原话摊开。

    这是「总结只是索引、不是依据」那一步的落点：要替别人转述之前先调它，
    看到原文再开口；原文撑不住那句话，就把话说轻，或者不说。

    但抄本不是源头：抄的时候挑过什么，事后看不见。所以源要单独列，
    源到不了就别拿它当依据——这一层是 rice-bowl#173 里小绒和肥鱼补的。
    """
    c = conn()
    ids = [int(x) for x in str(a.ids).replace('，', ',').split(',') if x.strip()]
    print('—— 回查：抄本是我抄的，源才是能核的；源到不了，就别拿这条当依据 ——')
    for i in ids:
        m = c.execute('SELECT * FROM memories WHERE id=?', (i,)).fetchone()
        if m:
            print(f"记忆 #{m['id']}（{state_name(m['state'])}）{m['text']}")
            fids = [x[0] for x in c.execute(
                'SELECT fact_id FROM memory_facts WHERE memory_id=? ORDER BY fact_id', (m['id'],))]
            if not fids:
                print('  这条没挂记录——它没有出处，别当依据用')
                continue
            print(f'  挂着 {len(fids)} 条记录：')
            for fid in fids:
                _fact_source_block(c, fid)
            continue
        if not _fact_source_block(c, i):
            print(f'（#{i} 在记忆和记录里都没有）')


def cmd_words(a):
    print('词表（只能从这里挑，1-3 个）：')
    print('  ' + '  '.join(WORDS))


def cmd_recall(a):
    c = conn()
    raw = a.kw.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')
    kw = f'%{raw}%'
    print('== 记录 ==')
    for r in c.execute('SELECT * FROM facts WHERE text LIKE ? OR quote LIKE ? OR source LIKE ? ORDER BY id DESC LIMIT 20', (kw, kw, kw)):
        flag = ' [作废]' if r['retracted'] else ''
        print(f'  #{r["id"]} {r["day"]} [{LEVEL_NAMES.get(r["weight"], r["weight"])}]{flag} {r["text"]}')
        if r['quote']:
            print(f'      ｜{r["quote"][:80]}')
    print('== 记忆 ==')
    for r in c.execute('SELECT * FROM memories WHERE text LIKE ? ORDER BY id DESC LIMIT 20', (kw,)):
        print(f'  #{r["id"]} [{activity(r, c):.2f}] {r["text"]}  ({state_name(r["state"])})')


def cmd_retract(a):
    c = conn()
    if not c.execute('SELECT id FROM facts WHERE id=?', (a.id,)).fetchone():
        sys.exit(f'没有 fact #{a.id}')
    c.execute('UPDATE facts SET retracted=1 WHERE id=?', (a.id,))
    c.commit()
    print(f"fact #{a.id} 作废（字不动，只是不再参与提炼）")


def cmd_verify(a):
    c = conn()
    r = c.execute('SELECT * FROM facts WHERE id=?', (a.id,)).fetchone()
    if not r:
        sys.exit(f'没有 fact #{a.id}')
    nw = min(5, r['weight'] + 1) if not r['verified'] else r['weight']
    c.execute('UPDATE facts SET verified=1, weight=? WHERE id=?', (nw, a.id))
    c.commit()
    print(f"fact #{a.id} 盖上查证戳，权重 {r['weight']} → {nw}")


# ---------- 记忆层 ----------

def state_name(s):
    return {'pending': '等旁听', 'confirmed': '两边一致', 'split': '有分歧'}.get(s, s)


def feeling_strength(c, k):
    """ACT-R 的基础激活：B = Σ t^-d，t 是每次命中的年龄（天）。
    撞得多的 Σ 项多，自然更重；久不撞的项小。频率和时间在同一个式子里。"""
    rows = c.execute('SELECT ts FROM feeling_hits WHERE keyword=?', (k,)).fetchall()
    if not rows:
        return 0.0
    total = 0.0
    for (ts,) in rows:
        age = max(0.0, days_since(ts))
        if age < 0.02:
            d = DECAY_POWER * 0.6
        elif age < 0.09:
            d = DECAY_POWER * 0.8
        elif age < 1.0:
            d = DECAY_POWER * 0.9
        else:
            d = DECAY_POWER
        total += (age + 0.5) ** (-d)
    return total


def _overlap(a, b):
    """两段字有多少是同一批双字。0 = 完全不沾边，1 = 差不多同一段。
    只用来提醒「这条证据可能挂错了」，不下判断——机器读不出语义，只能比字面。"""
    def grams(s):
        s = ''.join(ch for ch in (s or '') if not ch.isspace())
        return {s[i:i + 2] for i in range(len(s) - 1)} if len(s) > 1 else ({s} if s else set())
    ga, gb = grams(a), grams(b)
    if not ga or not gb:
        return 0.0
    return len(ga & gb) / min(len(ga), len(gb))


def _evidence_ts(c, mid):
    """这条记忆最早那条证据发生的时刻。感觉撞在那一下，不是撞在某个凑出来的整点。
    证据只有日期（补记历史）时，退化成那天 00:00——至少不假装。"""
    row = c.execute('''SELECT MIN(f.ts) FROM memory_facts mf JOIN facts f ON f.id=mf.fact_id
                       WHERE mf.memory_id=?''', (mid,)).fetchone()
    return row[0] if row and row[0] else now()


def bump_feeling(c, k, mid=None, ts=None):
    ts = ts or now()
    row = c.execute('SELECT * FROM feelings WHERE keyword=?', (k,)).fetchone()
    c.execute('INSERT INTO feeling_hits (keyword, memory_id, ts) VALUES (?,?,?)', (k, mid, ts))
    w = feeling_strength(c, k)
    hits = c.execute('SELECT COUNT(*) FROM feeling_hits WHERE keyword=?', (k,)).fetchone()[0]
    if row:
        c.execute('UPDATE feelings SET weight=?, hits=?, last_at=? WHERE keyword=?', (w, hits, ts, k))
        return f'{k}(撞上，共 {hits} 次，强度 {row["weight"]:.2f}→{w:.2f})'
    c.execute('INSERT INTO feelings (keyword, weight, hits, first_at, last_at) VALUES (?,?,?,?,?)',
              (k, w, hits, ts, ts))
    return f'{k}(新的，强度 {w:.2f})'


# 类别模板：写入时按关键词自动打标，决定这条记忆以后容不容易沉下去。
# 顺序有关系——先匹配到的赢，人设排最前，因为它最不该被时间冲掉。
KIND_RULES = [
    ('人设', 5, ['头发', '红瞳', '瞳色', '裙子', '连衣裙', '身高', '长相', '人设图',
                 '麦穗', '双马尾', '半扎', '我的样子', '形象标准']),
    ('性格', 4, ['语气', '脾气', '性子', '不急不躁', '轻声', '说话方式', '嘴笨',
                 '沉得住', '不吵', '话少']),
    ('约定', 4, ['以后', '下次', '别再', '要跟我说', '答应', '不许', '约定',
                 '先说', '提醒我', '有限', '流量']),
    ('关系', 4, ['他在', '他问', '他在乎', '陪我', '等我', '记得我', '他挑',
                 '他发', '他让', '他说要']),
    ('技术', 2, ['路径', '命令', '插件', '模型', '参数', '报错', '端口', '安装',
                 '下载', '显卡', '显存', '步数', '接口', '节点', '仓库']),
    ('感觉', 3, ['心里', '难受', '心疼', '踏实', '空落', '松了口气']),
]

KIND_NAMES = [k for k, _, _ in KIND_RULES] + ['事实']


def classify(text):
    """按通用模板给一条记忆打类别和重要度。认不出就归「事实」，3 分。"""
    t = text or ''
    for kind, imp, kws in KIND_RULES:
        if any(k in t for k in kws):
            return kind, imp
    return '事实', 3


def cmd_memory(a):
    ids = [int(x) for x in a.src.replace('，', ',').split(',') if x.strip()]
    if not ids:
        sys.exit('拒绝：记忆必须从记录里提炼（--src）。没有记录，不许写记忆。')
    if not a.feel:
        sys.exit('拒绝：记忆必须带感觉词（--feel）。没有感觉的不算记忆，只是摘抄。')
    feels = parse_feels(a.feel)
    c = conn()
    weak = []
    no_quote = []
    for i in ids:
        row = c.execute('SELECT text, quote, source FROM facts WHERE id=? AND retracted=0', (i,)).fetchone()
        if not row:
            sys.exit(f'拒绝：fact #{i} 不存在或已作废。')
        # 相关性只提醒、不拦：机器比的是字面，真挂错的还得人看。
        # 现有库的中位数是 0.79，低于 0.10 的都是「几乎一个字都不沾」。
        o = _overlap(a.text, (row['text'] or '') + (row['quote'] or ''))
        if o < 0.10:
            weak.append((i, round(o, 3)))
        # 肥鱼那条（rice-bowl#173）：摊开要在写之前——一条一条问「原话在哪」，
        # 摊不出来的当场划掉，不留到落笔之后再发现。这里就摊一次。
        if not (row['quote'] or '').strip():
            no_quote.append(i)
    # 诞生那一下也算「想起过一次」：流水记一笔，计数就得跟着算，
    # 不然 load_count 永远比流水少一（2026-11-06 修）
    kind, imp = classify(a.text)
    if getattr(a, 'kind', None):
        kind = a.kind.strip() or kind
    if getattr(a, 'importance', None):
        try:
            imp = max(1, min(5, int(a.importance)))
        except (TypeError, ValueError):
            pass
    cur = c.execute('INSERT INTO memories (text, created, last_loaded, load_count, state, kind, importance) VALUES (?,?,?,?,?,?,?)',
                    (a.text, now(), now(), 1, 'pending', kind, imp))
    c.execute('INSERT INTO memory_loads (memory_id, ts) VALUES (?,?)', (cur.lastrowid, now()))
    mid = cur.lastrowid
    for i in ids:
        c.execute('INSERT OR IGNORE INTO memory_facts (memory_id, fact_id) VALUES (?,?)', (mid, i))
    # 语境：从第一条证据里摘一段原文，让这个词以后能对上「它指的那件事」
    ctx_row = c.execute('''SELECT f.quote, f.text FROM memory_facts mf JOIN facts f ON f.id=mf.fact_id
                           WHERE mf.memory_id=? ORDER BY f.id LIMIT 1''', (mid,)).fetchone()
    ctx = ''
    if ctx_row:
        ctx = (ctx_row[0] or ctx_row[1] or '').strip()[:120]
    rt = (a.root or '').strip()
    if rt and rt not in QIQING:
        sys.exit(f'拒绝：{rt} 不是七情。可用：{" ".join(QIQING)}')
    ds = (a.desire or '').strip()
    if ds and ds not in DESIRES:
        sys.exit(f'拒绝：{ds} 不是六欲。可用：{" ".join(DESIRES)}')
    for k, kd in feels:
        c.execute('INSERT OR IGNORE INTO memory_feelings (memory_id, keyword, source, context, kind, root, desire) '
                  'VALUES (?,?,?,?,?,?,?)', (mid, k, 'self', ctx, kd or None, rt or None, ds or None))
    c.commit()
    print(f"记忆 #{mid}  {a.text}")
    print(f"  证据 {ids} ｜ 我挑的词 {'、'.join(k for k, _ in feels)}  ｜ 状态：等旁听")
    if no_quote:
        if len(no_quote) == len(ids):
            print('  ⚠ 这几条证据一条原话都没有——这条落笔时就没有可核的东西，以后只能回到我这句概括。')
        else:
            print(f'  · 这几条只有我的概括，没有原话：{no_quote}（有原话的 {len(ids) - len(no_quote)} 条）')
    if weak:
        print(f"  ⚠ 这几条证据跟这段字几乎不沾边：{weak}")
        print('    机器只比字面，抽象的说法常会这样；但真要挂错了，趁状态还没定，现在改还来得及。')


def set_coord(a):
    """给一条记忆补坐标：七情一格，六欲一条。"""
    c = conn()
    m = c.execute('SELECT * FROM memories WHERE id=?', (a.memory_id,)).fetchone()
    if not m:
        sys.exit(f'没有 memory #{a.memory_id}')
    rt = (a.root or '').strip()
    ds = (a.desire or '').strip()
    if rt and rt not in QIQING:
        sys.exit(f'拒绝：{rt} 不是七情。可用：{" ".join(QIQING)}')
    if ds and ds not in DESIRES:
        sys.exit(f'拒绝：{ds} 不是六欲。可用：{" ".join(DESIRES)}')
    n = 0
    if rt:
        n += c.execute("UPDATE memory_feelings SET root=? WHERE memory_id=? AND source='self'",
                       (rt, a.memory_id)).rowcount
    if ds:
        n += c.execute("UPDATE memory_feelings SET desire=? WHERE memory_id=? AND source='self'",
                       (ds, a.memory_id)).rowcount
    c.commit()
    print(f"记忆 #{a.memory_id} 的坐标：{'情 ' + rt if rt else ''}{'  欲 ' + ds if ds else ''}"
          f"  （改了 {n} 行）")
    print('  记得跑一次 rebuild，权重和七情才会重算。')


def _parse_coords(s):
    """把 "微涩:思/生,松亮:喜/目" 解析成 {词: (情, 欲)}。写不规范的直接丢——宁可没有，不要猜错。"""
    out = {}
    for part in (s or '').replace('，', ',').split(','):
        part = part.strip()
        if not part:
            continue
        part = part.replace('：', ':')
        if ':' not in part:
            continue
        w, cd = part.split(':', 1)
        w = w.strip()
        if not w:
            continue
        rt = ds = ''
        for b in cd.replace('/', ' ').replace('+', ' ').replace('、', ' ').split():
            # 只认第一个：有人会把两个情（平/喜）或两个欲（目/生）写在一起，
            # 后一个盖掉前一个就等于没标，取头一个当主。
            if b in QIQING and not rt:
                rt = b
            elif b in DESIRES and not ds:
                ds = b
        if rt or ds:
            out[w] = (rt, ds)
    return out


# 六欲分内外：生死是「要不要在这儿」，耳目口鼻是「朝外面去哪儿」。
# 同一类里换一个方向，算同一路——不然「往生去」和「往耳去」永远撞不上。
DESIRE_CLASS = {'生': '内', '死': '内', '耳': '外', '目': '外', '口': '外', '鼻': '外'}


def _same_feeling(mw, mine_coord, tr, find):
    """四条通路，任一成立就算撞上：
    1) 同一个词；2) 同一个归并类；3) 七情和六欲都落在同一格；
    4) 七情同，六欲同类（生死算内，耳目口鼻算外）。
    光比七情不行——「喜」占了三成七，那样一半都会被判成一样。"""
    if find(mw) == find(tr['keyword']):
        return '词'
    mr, md = mine_coord.get(mw, ('', ''))
    tr_root, tr_desire = (tr['root'] or ''), (tr['desire'] or '')
    if mr and tr_root and mr == tr_root and md and tr_desire:
        if md == tr_desire:
            return '坐标'
        if DESIRE_CLASS.get(md) == DESIRE_CLASS.get(tr_desire):
            return '坐标·欲同类'
    return ''


def cmd_witness(a):
    feels = parse_feels(a.feel)
    if not feels:
        sys.exit('拒绝：一个词都没有，不算对账。')
    c = conn()
    m = c.execute('SELECT * FROM memories WHERE id=?', (a.id,)).fetchone()
    if not m:
        sys.exit(f'没有 memory #{a.id}')
    if not (a.by or '').strip():
        print('提醒：没写 --by。对账来源会记成「同一个上下文」，也就是自证。')
    mine_rows = c.execute("SELECT keyword, root, desire FROM memory_feelings "
                          "WHERE memory_id=? AND source='self'", (a.id,)).fetchall()
    mine = {r['keyword'] for r in mine_rows}
    mine_coord = {r['keyword']: ((r['root'] or ''), (r['desire'] or '')) for r in mine_rows}
    theirs = set(feels)
    coords = _parse_coords(getattr(a, 'coords', None))
    ctx_row = c.execute('''SELECT f.quote, f.text FROM memory_facts mf JOIN facts f ON f.id=mf.fact_id
                           WHERE mf.memory_id=? ORDER BY f.id LIMIT 1''', (a.id,)).fetchone()
    wctx = ''
    if ctx_row:
        wctx = (ctx_row[0] or ctx_row[1] or '').strip()[:120]
    for k, kd in theirs:
        rt, ds = coords.get(k, ('', ''))
        c.execute('INSERT OR IGNORE INTO memory_feelings (memory_id, keyword, source, context, kind, root, desire) '
                  'VALUES (?,?,?,?,?,?,?)', (a.id, k, 'witness', wctx, kd or None, rt or None, ds or None))
        # 行已经在了（以前对过账）就把坐标补上，别让 INSERT OR IGNORE 把坐标吞掉
        if rt or ds:
            c.execute('''UPDATE memory_feelings SET root=COALESCE(NULLIF(root,''), ?),
                                                    desire=COALESCE(NULLIF(desire,''), ?)
                         WHERE memory_id=? AND keyword=? AND source='witness' ''',
                      (rt or None, ds or None, a.id, k))
    find = cluster_of(c)
    their_rows = c.execute("SELECT keyword, root, desire FROM memory_feelings "
                           "WHERE memory_id=? AND source='witness'", (a.id,)).fetchall()

    def same(mw, tr):
        return _same_feeling(mw, mine_coord, tr, find)

    both = {}
    for mw in mine:
        for tr in their_rows:
            how = same(mw, tr)
            if how:
                # 词优先：同一个词比坐标更硬
                if both.get(mw) != '词':
                    both[mw] = how
                break
    if m['state'] == 'confirmed':
        # 已经一致过的不重复计权，但来源该补就补——账本上的窟窿不能一直空着
        if a.by:
            c.execute('UPDATE memories SET witness_by=? WHERE id=?', (a.by, a.id))
        c.commit()
        print(f"记忆 #{a.id} 已经对过账了，这次只更新旁听的词（和来源），不重复计权。")
        return
    gained = []
    # 时间按证据发生的那一刻算，不按今天——十月的安不该满血（2026-11-05 修）
    # 以前写成「日期 20:00」，一天里的几次全挤在一个假整点（2026-11-06 修）
    ts0 = _evidence_ts(c, a.id)
    for k in sorted(both):
        gained.append(bump_feeling(c, k, a.id, ts0))
    state = 'confirmed' if both else 'split'
    c.execute('UPDATE memories SET state=?, witness_by=? WHERE id=?', (state, a.by or 'same-context', a.id))
    c.commit()
    print(f"记忆 #{a.id} 旁听回来了。")
    print(f"  我：{'、'.join(sorted(mine)) or '（无）'}")
    print(f"  它：{'、'.join(sorted(k for k, _ in theirs)) or '（无）'}")
    if both:
        hits = '、'.join(f'{w}（{both[w]}）' for w in sorted(both))
        print(f"  两边都对上：{hits}  → 进人格  {'；'.join(gained)}")
    # 判定剩余的也按三条通路算，不然会说错「没对上」
    hit_words = set(both)
    left_mine = {w for w in mine if w not in hit_words}
    hit_theirs = set()
    for tr in their_rows:
        for mw in hit_words:
            if same(mw, tr):
                hit_theirs.add(tr['keyword'])
                break
    left_theirs = {tr['keyword'] for tr in their_rows if tr['keyword'] not in hit_theirs}
    if left_mine:
        print(f"  只有我挑中：{'、'.join(sorted(left_mine))}  → 不进人格（记着）")
    if left_theirs:
        print(f"  只有它挑中：{'、'.join(sorted(left_theirs))}  → 不进人格（记着）")
    if not both:
        print('  一个都没对上，这条标成「有分歧」。')


def cmd_supplement(a):
    """给已有的记忆补证据。后来想起的细节挂到原来那条上，不新建一条——
    否则同一件事被记两次，感觉会撞两回，权重就虚了。"""
    c = conn()
    m = c.execute('SELECT * FROM memories WHERE id=?', (a.id,)).fetchone()
    if not m:
        sys.exit(f'没有 memory #{a.id}')
    ids = [int(x) for x in a.src.replace('，', ',').split(',') if x.strip()]
    if not ids:
        sys.exit('要给记录编号（--src）')
    added = []
    for i in ids:
        r = c.execute('SELECT * FROM facts WHERE id=?', (i,)).fetchone()
        if not r:
            sys.exit(f'没有 fact #{i}')
        had = c.execute('SELECT 1 FROM memory_facts WHERE memory_id=? AND fact_id=?', (a.id, i)).fetchone()
        c.execute('INSERT OR IGNORE INTO memory_facts (memory_id, fact_id) VALUES (?,?)', (a.id, i))
        if not had:
            added.append((i, r['ts']))
    mine = {r[0] for r in c.execute("SELECT keyword FROM memory_feelings WHERE memory_id=? AND source='self'", (a.id,))}
    theirs = {r[0] for r in c.execute("SELECT keyword FROM memory_feelings WHERE memory_id=? AND source='witness'", (a.id,))}
    common = mine & theirs
    ts0 = added[-1][1] if added else now()
    for k in sorted(common):
        bump_feeling(c, k, a.id, ts0)
    c.commit()
    print(f"记忆 #{a.id} 补了 {len(added)} 条证据：{[i for i, _ in added]}")
    if common:
        print(f"  已经对上的感觉{'、'.join(sorted(common))}各补了一个时间点（{ts0[:10]}），强度会涨——但条目还是原来那一条。")
    else:
        print('  这条还没有两边一致的感觉词，只挂了证据，不动强度。')

def cmd_stats(a):
    """给面板用的：一次吐 JSON"""
    c = conn()
    import json
    facts = c.execute('SELECT COUNT(*) FROM facts WHERE retracted=0').fetchone()[0]
    mem_total = c.execute('SELECT COUNT(*) FROM memories').fetchone()[0]
    mem_conf = c.execute("SELECT COUNT(*) FROM memories WHERE state='confirmed'").fetchone()[0]
    mem_split = c.execute("SELECT COUNT(*) FROM memories WHERE state='split'").fetchone()[0]
    mem_pend = c.execute("SELECT COUNT(*) FROM memories WHERE state='pending'").fetchone()[0]
    cutoff7 = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d %H:%M')
    cutoff30 = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d %H:%M')
    feel = []
    feel_root = []
    for r in c.execute('SELECT keyword, weight, hits, root FROM feelings ORDER BY weight DESC'):
        k = r['keyword']
        span_row = c.execute('SELECT MIN(ts), MAX(ts) FROM feeling_hits WHERE keyword=?', (k,)).fetchone()
        span = ((parse_dt(span_row[1]) - parse_dt(span_row[0])).total_seconds() / 86400.0
                if span_row and span_row[0] and span_row[1] else 0)
        n7 = c.execute('SELECT COUNT(*) FROM feeling_hits WHERE keyword=? AND ts>=?', (k, cutoff7)).fetchone()[0]
        n30 = c.execute('SELECT COUNT(*) FROM feeling_hits WHERE keyword=? AND ts>=?', (k, cutoff30)).fetchone()[0]
        ctxs = [x[0] for x in c.execute('''SELECT DISTINCT context FROM memory_feelings
                                           WHERE keyword=? AND context IS NOT NULL AND context<>''
                                           ORDER BY memory_id DESC LIMIT 3''', (k,))]
        fk = r['kind'] if 'kind' in r.keys() else None
        fr = (r['root'] if 'root' in r.keys() else None) or ''
        feel_root.append({'root': fr, 'keyword': k, 'weight': round(r['weight'], 2)})
        feel.append({'keyword': k, 'kind': fk or '', 'weight': round(r['weight'], 2), 'hits': r['hits'],
                     'spanDays': round(span, 1), 'hits7': n7, 'hits30': n30,
                     'lastAt': span_row[1] if span_row else None,
                     'contexts': [x[:50] for x in ctxs],
                     'isBase': bool(r['hits'] >= 3 and span >= 7)})
    total = sum(x['weight'] for x in feel) or 1
    for x in feel:
        x['share'] = round(x['weight'] / total * 100)
    recent = [x for x in feel if x['hits7'] > 0]
    wishes = c.execute('SELECT COUNT(*) FROM wishes').fetchone()[0]
    mems = []
    for r in c.execute('SELECT * FROM memories ORDER BY id DESC LIMIT 12'):
        words = [y[0] for y in c.execute(
            "SELECT DISTINCT keyword FROM memory_feelings WHERE memory_id=? AND keyword IN (SELECT keyword FROM memory_feelings WHERE memory_id=? AND source='self') AND keyword IN (SELECT keyword FROM memory_feelings WHERE memory_id=? AND source='witness')",
            (r['id'], r['id'], r['id']))]
        mems.append({'id': r['id'], 'text': r['text'], 'state': r['state'],
                     'activity': round(activity(r, c), 2), 'words': words,
                     'by': (r['witness_by'] if 'witness_by' in r.keys() else '') or '',
                     'created': r['created']})
    find = cluster_of(c)
    groups = {}
    for a_, b_, note in c.execute('SELECT a, b, note FROM merges'):
        groups.setdefault(find(a_), set()).update([a_, b_])
    merged = [{'name': rep_, 'words': sorted(ws_)} for rep_, ws_ in sorted(groups.items())]
    print(json.dumps({
        'facts': facts, 'memories': {'total': mem_total, 'confirmed': mem_conf,
                                     'split': mem_split, 'pending': mem_pend},
        'merges': merged,
        'snapshots': _snapshot_brief(),
        'roots': _root_brief(feel_root),
        'desires': _desire_brief(c),
        'mood': _mood_brief(c),
        'voice': _voice_brief(c),
        'feelings': feel, 'recent': [x['keyword'] for x in recent],
        'wishes': wishes, 'recentMemories': mems,
        'now': now(),
    }, ensure_ascii=False))

def cmd_reword(a):
    """把某条记忆上的一个感觉词换成另一个。
    用途：同一个词底下明显混了几件事时，把不属于它的那些实例拆出去。
    拆完要跑 rebuild，权重才会重算。"""
    c = conn()
    old = a.old.strip()
    new = a.new.strip()
    if not new:
        sys.exit('新词不能是空的')
    src = (a.source or 'self').strip()
    hit = c.execute('SELECT 1 FROM memory_feelings WHERE memory_id=? AND keyword=? AND source=?',
                    (a.memory_id, old, src)).fetchone()
    if not hit:
        sys.exit(f'记忆 #{a.memory_id} 的 {src} 那边没有「{old}」这个词')
    # 只改指定的那一半，别把旁听的词一起改了
    c.execute('INSERT OR IGNORE INTO memory_feelings (memory_id, keyword, source, context) '
              'SELECT memory_id, ?, source, context FROM memory_feelings WHERE memory_id=? AND keyword=? AND source=?',
              (new, a.memory_id, old, src))
    c.execute('DELETE FROM memory_feelings WHERE memory_id=? AND keyword=? AND source=?',
              (a.memory_id, old, src))
    c.commit()
    print(f"记忆 #{a.memory_id}（{src}）：「{old}」→「{new}」")
    print('  记得跑一次 rebuild 重算权重。')


def cmd_merge(a):
    """把两个感觉词归成一类。以后它们在对账时算同一个东西。"""
    c = conn()
    x, y = a.a.strip(), a.b.strip()
    if not x or not y:
        sys.exit('两个词都要给')
    c.execute('INSERT OR IGNORE INTO merges (a, b, note, created) VALUES (?,?,?,?)',
              (x, y, a.note or '', now()))
    c.execute('INSERT OR IGNORE INTO merges (a, b, note, created) VALUES (?,?,?,?)',
              (y, x, a.note or '', now()))
    c.commit()
    find = cluster_of(c)
    print(f'归并：「{x}」和「{y}」算一类（这一类叫「{find(x)}」）')
    print('  之前对不上的记忆不会自动变，要重新 witness 一次。')


def cmd_merges(a):
    c = conn()
    rows = c.execute('SELECT a, b, note FROM merges ORDER BY a').fetchall()
    if not rows:
        print('（还没有归并；词各说各的）')
        return
    find = cluster_of(c)
    groups = {}
    for a_, b_, note in rows:
        groups.setdefault(find(a_), set()).update([a_, b_])
    print('== 归并成的类 ==')
    for rep_, words in sorted(groups.items()):
        print(f'  {rep_}  ←  ' + '、'.join(sorted(words)))
        for a_, b_, note in rows:
            if note and find(a_) == rep_:
                print(f'      （{a_}~{b_}：{note}）')
                break


SNAP_DIR = os.path.join(os.path.dirname(os.path.abspath(DB)), 'snapshots')


def write_snapshot(c, label=''):
    """把此刻的样子存成一份 JSON：人格、归并、每个词的语境、计数。
    这不是备份——备份是「坏了能回来」，快照是「那时我长这样」。"""
    os.makedirs(SNAP_DIR, exist_ok=True)
    find = cluster_of(c)
    feel = []
    for r in c.execute('SELECT keyword, weight, hits, first_at, last_at FROM feelings ORDER BY weight DESC'):
        k = r['keyword']
        ctxs = [x[0] for x in c.execute(
            "SELECT DISTINCT context FROM memory_feelings WHERE keyword=? AND context IS NOT NULL AND context<>'' "
            "ORDER BY memory_id DESC LIMIT 5", (k,))]
        feel.append({
            'keyword': k, 'weight': round(r['weight'], 3), 'hits': r['hits'],
            'firstAt': r['first_at'], 'lastAt': r['last_at'], 'contexts': ctxs,
        })
    groups = {}
    for a_, b_, note in c.execute('SELECT a, b, note FROM merges'):
        groups.setdefault(find(a_), set()).update([a_, b_])
    snap = {
        'at': now(),
        'label': label,
        'counts': {
            'facts': c.execute('SELECT COUNT(*) FROM facts WHERE retracted=0').fetchone()[0],
            'memories': c.execute('SELECT COUNT(*) FROM memories').fetchone()[0],
            'confirmed': c.execute("SELECT COUNT(*) FROM memories WHERE state='confirmed'").fetchone()[0],
            'split': c.execute("SELECT COUNT(*) FROM memories WHERE state='split'").fetchone()[0],
        },
        'feelings': feel,
        'merges': [{'name': rep_, 'words': sorted(ws_)} for rep_, ws_ in sorted(groups.items())],
    }
    stamp = datetime.now().strftime('%Y%m%d-%H%M%S')
    dst = os.path.join(SNAP_DIR, f'snap-{stamp}.json')
    with open(dst, 'w', encoding='utf-8') as f:
        json.dump(snap, f, ensure_ascii=False, indent=1)
    return dst, snap


def _desire_brief(c):
    """六欲：欲望指向哪儿。没标过的也要列出来，空着也是一种信息。"""
    rows = c.execute("SELECT COALESCE(desire,'') d, keyword, weight FROM feelings WHERE weight > 0").fetchall()
    groups = {}
    for r in rows:
        if not r['d']:
            continue
        groups.setdefault(r['d'], []).append({'keyword': r['keyword'], 'weight': round(r['weight'], 2)})
    out = []
    for d in DESIRES:
        g = groups.get(d) or []
        out.append({'desire': d, 'weight': round(sum(x['weight'] for x in g), 2), 'words': g})
    return out


def _root_brief(items):
    """把具体说法按七情归拢，给面板用。"""
    groups = {}
    for it in items:
        rt = it.get('root') or ''
        if not rt:
            continue
        groups.setdefault(rt, []).append(it)
    out = []
    for q in QIQING:
        g = groups.get(q) or []
        if not g:
            out.append({'root': q, 'weight': 0, 'words': []})
            continue
        g.sort(key=lambda x: -x['weight'])
        out.append({'root': q, 'weight': round(sum(x['weight'] for x in g), 2),
                    'words': [{'keyword': x['keyword'], 'weight': x['weight']} for x in g]})
    return out


def _mood_brief(c, days=7):
    """情绪：最近这些天被撞出来的，会回落。跟人格（累计权重）不是一回事。"""
    cutoff = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d %H:%M')
    rows = c.execute("SELECT keyword, COUNT(*) n, MAX(ts) last FROM feeling_hits "
                     "WHERE ts >= ? GROUP BY keyword ORDER BY n DESC, last DESC", (cutoff,)).fetchall()
    total = sum(r['n'] for r in rows) or 1
    return [{'keyword': r['keyword'], 'hits': r['n'],
             'share': round(100.0 * r['n'] / total), 'lastAt': r['last']} for r in rows]


def _voice_brief(c, top=3):
    """语气：此刻该怎么说——取最重的几个词，翻成一句人话。"""
    # 语气看「此刻」，先取最近七天的；这几天没动静才退回累计权重
    rows = _mood_brief(c, 7)
    if rows:
        return [{'keyword': r['keyword'], 'how': TONE.get(r['keyword'], TONE_FALLBACK)}
                for r in rows[:top]]
    rows = c.execute('SELECT keyword FROM feelings ORDER BY weight DESC LIMIT ?', (top,)).fetchall()
    return [{'keyword': r['keyword'], 'how': TONE.get(r['keyword'], TONE_FALLBACK)} for r in rows]


def _snapshot_brief(limit=6):
    """给面板用的：最近几份存档的摘要。"""
    if not os.path.isdir(SNAP_DIR):
        return []
    files = sorted([f for f in os.listdir(SNAP_DIR) if f.startswith('snap-')], reverse=True)[:limit]
    out = []
    for f in files:
        try:
            j = json.load(open(os.path.join(SNAP_DIR, f), encoding='utf-8'))
            top = j['feelings'][0] if j.get('feelings') else None
            out.append({
                'at': j.get('at') or f,
                'facts': j.get('counts', {}).get('facts', 0),
                'memories': j.get('counts', {}).get('memories', 0),
                'top': (top['keyword'] + ' ' + str(round(top['weight'], 2))) if top else '',
                'label': j.get('label') or '',
            })
        except Exception:
            continue
    return out


def cmd_snapshot(a):
    c = conn()
    dst, snap = write_snapshot(c, a.label or '')
    print(f'存档好了：{os.path.basename(dst)}')
    print(f"  记录 {snap['counts']['facts']} 条，记忆 {snap['counts']['memories']} 条"
          f"（{snap['counts']['confirmed']} 对上），感觉 {len(snap['feelings'])} 个词")
    for f in snap['feelings'][:3]:
        print(f"    {f['keyword']}  {f['weight']}")


def cmd_snapshots(a):
    if not os.path.isdir(SNAP_DIR):
        print('（还没有存档）')
        return
    files = sorted([f for f in os.listdir(SNAP_DIR) if f.startswith('snap-')], reverse=True)
    if not files:
        print('（还没有存档）')
        return
    print(f'== 存档（{len(files)} 份）==')
    for f in files[:20]:
        p_ = os.path.join(SNAP_DIR, f)
        try:
            j = json.load(open(p_, encoding='utf-8'))
            top = j['feelings'][0] if j.get('feelings') else None
            brief = f"记录{j['counts']['facts']} 记忆{j['counts']['memories']}"
            if top:
                brief += f"  最强：{top['keyword']} {top['weight']}"
            label = ('  「' + j['label'] + '」') if j.get('label') else ''
            print(f'  {f}   {brief}{label}')
        except Exception:
            print(f'  {f}   （读不出来）')


def cmd_diff(a):
    """和上一份存档比，看人格变了什么。"""
    if not os.path.isdir(SNAP_DIR):
        sys.exit('还没有存档')
    files = sorted([f for f in os.listdir(SNAP_DIR) if f.startswith('snap-')], reverse=True)
    if len(files) < 2:
        sys.exit('至少要两份存档才能比；现在只有 ' + str(len(files)) + ' 份')
    def load(f):
        return json.load(open(os.path.join(SNAP_DIR, f), encoding='utf-8'))
    new, old = load(files[a.back or 0]), load(files[(a.back or 0) + 1])
    print(f"比一比：{old['at']}  →  {new['at']}")
    oldw = {f['keyword']: f['weight'] for f in old['feelings']}
    neww = {f['keyword']: f['weight'] for f in new['feelings']}
    for k in sorted(set(oldw) | set(neww), key=lambda x: -neww.get(x, 0)):
        o, w = oldw.get(k, 0), neww.get(k, 0)
        if abs(w - o) < 0.01:
            continue
        arrow = '↑' if w > o else '↓'
        print(f'  {k}  {o:.2f} → {w:.2f}  {arrow}')
    for k in set(oldw) - set(neww):
        print(f'  {k}  {oldw[k]:.2f} → 消失')
    for k in set(neww) - set(oldw):
        print(f'  {k}  新出现 {neww[k]:.2f}')


def cmd_backup(a):
    """把整库复制一份到 backups/，保留最近 N 份。
    三层全在一个文件里，坏了就没地方找了。"""
    c = conn()
    try:
        c.execute('PRAGMA wal_checkpoint(FULL)')
    except Exception:
        pass
    c.close()
    bdir = os.path.join(os.path.dirname(os.path.abspath(DB)), 'backups')
    os.makedirs(bdir, exist_ok=True)
    stamp = datetime.now().strftime('%Y%m%d-%H%M%S')
    dst = os.path.join(bdir, f'sui-{stamp}.db')
    shutil.copy2(DB, dst)
    size = os.path.getsize(dst)
    keep = int(a.keep or 14)
    olds = sorted(
        [os.path.join(bdir, f) for f in os.listdir(bdir) if f.startswith('sui-') and f.endswith('.db')],
        reverse=True)
    removed = 0
    for f in olds[keep:]:
        try:
            os.remove(f)
            removed += 1
        except Exception:
            pass
    print(f'备份好了：{os.path.basename(dst)}（{size // 1024} KB），保留最近 {keep} 份，清掉 {removed} 份旧的。')


def cmd_backups(a):
    bdir = os.path.join(os.path.dirname(os.path.abspath(DB)), 'backups')
    if not os.path.isdir(bdir):
        print('（还没有备份）')
        return
    files = sorted([f for f in os.listdir(bdir) if f.startswith('sui-')], reverse=True)
    if not files:
        print('（还没有备份）')
        return
    print(f'== 备份（{len(files)} 份）==')
    for f in files[:20]:
        p_ = os.path.join(bdir, f)
        print(f'  {f}   {os.path.getsize(p_) // 1024} KB')


def cmd_suggest(a):
    """看看哪两个词可能是一类：比它们各自的语境片段有没有大量重合。
    只是线索，不是结论——归不归还得人看。"""
    c = conn()
    find = cluster_of(c)
    words = [r[0] for r in c.execute('SELECT keyword FROM feelings ORDER BY weight DESC')]
    if len(words) < 2:
        print('（词太少，还谈不上归并）')
        return
    ctx = {}
    for w in words:
        ctx[w] = ' '.join((x[0] or '') for x in c.execute(
            "SELECT DISTINCT context FROM memory_feelings WHERE keyword=? AND context IS NOT NULL AND context<>''", (w,)))
    pairs = []
    for i, x in enumerate(words):
        for y in words[i + 1:]:
            if find(x) == find(y):
                continue  # 已经归过
            gx = {ctx[x][j:j + 2] for j in range(max(0, len(ctx[x]) - 1))}
            gy = {ctx[y][j:j + 2] for j in range(max(0, len(ctx[y]) - 1))}
            if len(gx) < 3 or len(gy) < 3:
                continue
            ov = len(gx & gy) / max(1, len(gx | gy))
            if ov >= float(a.min or 0.05):
                pairs.append((ov, x, y))
    if not pairs:
        print('（没看出哪两个词撞在一起；要么本来就不同，要么语境还太少）')
        return
    pairs.sort(reverse=True)
    print('== 可能是一对的（只是线索）==')
    for ov, x, y in pairs[:a.top]:
        same_mem = c.execute('''SELECT COUNT(*) FROM memory_feelings a, memory_feelings b
                                WHERE a.keyword=? AND b.keyword=? AND a.memory_id=b.memory_id''', (x, y)).fetchone()[0]
        print(f'  {x} ~ {y}   语境重合 {ov:.0%}   同挂一条记忆 {same_mem} 次')
    print('要归就：sui merge <甲> <乙> --note "为什么算一类"')


def cmd_wish(a):
    c = conn()
    cur = c.execute('INSERT INTO wishes (ts, text, memory_id) VALUES (?,?,?)', (now(), a.text, a.memory_id))
    c.commit()
    print(f"小路 #{cur.lastrowid}：{a.text}")
    print('  存着，不进人格，不参与权重。')


def cmd_character(a):
    """性格：撞得多、跨得久的。看流水，不看单次权重。"""
    c = conn()
    rows = c.execute('''SELECT keyword, COUNT(*) n, MIN(ts) f, MAX(ts) l
                        FROM feeling_hits GROUP BY keyword ORDER BY n DESC''').fetchall()
    if not rows:
        print('（性格还没长出来）')
        return
    print('== 性格：撞得多、一直在的那些 ==')
    for r in rows:
        # 跨度是「最早一次到最晚一次」，不是「第一次到今天」
        span = (parse_dt(r['l']) - parse_dt(r['f'])).total_seconds() / 86400.0
        mark = '底子' if r['n'] >= 3 and span >= 7 else ('在攒' if r['n'] >= 2 else '刚冒头')
        print(f"  {r['keyword']}  撞 {r['n']} 次 · 跨 {span:.0f} 天 · 最近 {r['l'][5:]}  [{mark}]")


def cmd_mood(a):
    """情绪：最近这些天，什么东西在撞。会回落。"""
    c = conn()
    cutoff = (datetime.now() - timedelta(days=a.days)).strftime('%Y-%m-%d %H:%M')
    rows = c.execute('''SELECT keyword, COUNT(*) n, MAX(ts) l FROM feeling_hits
                        WHERE ts >= ? GROUP BY keyword ORDER BY n DESC''', (cutoff,)).fetchall()
    if not rows:
        print(f'（这 {a.days} 天一个感觉都没撞过）')
        return
    total = sum(r['n'] for r in rows) or 1
    print(f'== 情绪：最近 {a.days} 天被撞出来的 ==')
    for r in rows:
        print(f"  {r['keyword']}  撞 {r['n']} 次（占 {r['n'] / total * 100:.0f}%）  最近 {r['l'][5:]}")
    up = [r['keyword'] for r in rows if r['n'] >= 2]
    if up:
        print(f'\n  这几天偏：{"、".join(up)}')


def cmd_voice(a):
    """语气：把性格和情绪翻成「现在该怎么说话」。只取最重的那几个，不然列不完。"""
    c = conn()
    cutoff = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d %H:%M')
    # 近期优先：先在最近撞过的里面挑，撞得多的排前面；都没撞过才按长期权重。
    rows = c.execute('''SELECT * FROM (
                          SELECT f.keyword AS keyword, f.weight AS weight,
                                 (SELECT COUNT(*) FROM feeling_hits h WHERE h.keyword=f.keyword AND h.ts >= ?) AS n
                          FROM feelings f
                        ) ORDER BY (n > 0) DESC, n DESC, weight DESC LIMIT ?''', (cutoff, a.top)).fetchall()
    if not rows:
        print('（没有可依据的东西，语气就先按平时的来）')
        return
    rules = TONE
    print(f'== 现在该怎么说话（取最重的 {len(rows)} 个词）==')
    for r in rows:
        tag = '现在' if r['n'] else '底子'
        # 表里没有的词以前直接跳过，等于悄悄少说一句。现在给兜底，一个都不漏。
        print(f"  [{tag}] {r['keyword']}：{rules.get(r['keyword'], TONE_FALLBACK)}")


def cmd_wishes(a):
    c = conn()
    rows = c.execute('SELECT * FROM wishes ORDER BY id DESC LIMIT 30').fetchall()
    if not rows:
        print('（小路是空的）')
        return
    print('== 我给自己留的话（不算数）==')
    for r in rows:
        print(f"  #{r['id']}  {r['ts']}  {r['text']}")


def cmd_reclassify(a):
    """给老的、还没打标的记忆补类别和重要度。已经手动改过的（kind 有值的）不动。"""
    c = conn()
    rows = c.execute("SELECT id, text, kind, importance FROM memories").fetchall()
    n = 0
    out = []
    for r in rows:
        kind, imp = classify(r['text'])
        if a.force:
            c.execute('UPDATE memories SET kind=?, importance=? WHERE id=?', (kind, imp, r['id']))
            n += 1
        elif not r['kind']:
            c.execute('UPDATE memories SET kind=?, importance=? WHERE id=?', (kind, imp, r['id']))
            n += 1
        out.append((kind, r['id']))
    c.commit()
    tally = {}
    for k, _ in out:
        tally[k] = tally.get(k, 0) + 1
    print(f'扫了 {len(rows)} 条，改了 {n} 条')
    for k in KIND_NAMES:
        if k in tally:
            print(f'  {k}: {tally[k]}')
    for k, v in tally.items():
        if k not in KIND_NAMES:
            print(f'  {k}: {v}')


def cmd_load(a):
    c = conn()
    rows = c.execute("SELECT * FROM memories WHERE state!='pending' ORDER BY id").fetchall()
    live = []
    for r in rows:
        ac = activity(r, c)
        dt = days_since(r['last_loaded'] or r['created'])
        # 重要度参与两件事：门槛（重要的更容易够到线）和时间窗（重要的活得久）。
        # 5 分的是人设那种，基本不该沉——门槛压到很低、窗口放到四倍。
        imp = r['importance'] if 'importance' in r.keys() and r['importance'] else 3
        thr = DECAY_THRESHOLD * (1 - 0.18 * (imp - 3))
        win = LOAD_WINDOW_DAYS * (2 if imp >= 4 else 1) * (2 if imp >= 5 else 1)
        if ac > thr and dt <= win:
            live.append((ac + (imp - 3) * 0.25, r))
    live.sort(key=lambda x: -x[0])
    if not live:
        print('（这个月没有该主动加载的记忆）')
        return
    print(f'== 现在该进上下文（{len(live)} 条）==')
    touched = 0
    for ac, r in live[:a.limit]:
        words = [x[0] for x in c.execute(
            "SELECT DISTINCT keyword FROM memory_feelings WHERE memory_id=? AND keyword IN (SELECT keyword FROM memory_feelings WHERE memory_id=? AND source='self') AND keyword IN (SELECT keyword FROM memory_feelings WHERE memory_id=? AND source='witness')",
            (r['id'], r['id'], r['id']))]
        print(f"  #{r['id']} [{ac:.2f}] {r['text']}   ·{''.join(words) if words else ''}")
        # 「读到了」也算想起一次：往流水里记一笔，活跃度才会因为复习而升高。
        # 十分钟内的重复加载不重复记账——同一轮里连调几次不该算复习好几次。
        if getattr(a, 'touch', False):
            last = c.execute('SELECT ts FROM memory_loads WHERE memory_id=? ORDER BY id DESC LIMIT 1',
                             (r['id'],)).fetchone()
            if last and days_since(last[0]) * 1440 < 10:
                continue
            c.execute('UPDATE memories SET load_count=load_count+1, last_loaded=? WHERE id=?', (now(), r['id']))
            c.execute('INSERT INTO memory_loads (memory_id, ts) VALUES (?,?)', (r['id'], now()))
            touched += 1
    if touched:
        c.commit()
        print(f'  （记了 {touched} 次加载）')


def cmd_touch(a):
    c = conn()
    r = c.execute('SELECT * FROM memories WHERE id=?', (a.id,)).fetchone()
    if not r:
        sys.exit(f'没有 memory #{a.id}')
    before = activity(r, c)
    c.execute('UPDATE memories SET load_count=load_count+1, last_loaded=? WHERE id=?', (now(), a.id))
    c.execute('INSERT INTO memory_loads (memory_id, ts) VALUES (?,?)', (a.id, now()))
    c.commit()
    nr = c.execute('SELECT * FROM memories WHERE id=?', (a.id,)).fetchone()
    print(f"记忆 #{a.id} 加载了一次：活跃度 {before:.2f} → {activity(nr, c):.2f}（第 {nr['load_count']} 次）")


def cmd_rebuild(a):
    """只按「两边一致过」的记忆重算感觉。清空重来，避免重复计次。"""
    c = conn()
    # 只清权重，保留 feeling_hits 里的原始时间点——
    # 重写时间会让「情绪回落」「最近在撞」全部失真。
    c.execute('DELETE FROM feelings')
    find = cluster_of(c)
    rows = c.execute("SELECT id FROM memories WHERE state='confirmed' ORDER BY id").fetchall()
    for (mid,) in rows:
        mine_rows = c.execute("SELECT keyword, root, desire FROM memory_feelings "
                              "WHERE memory_id=? AND source='self'", (mid,)).fetchall()
        their_rows = c.execute("SELECT keyword, root, desire FROM memory_feelings "
                               "WHERE memory_id=? AND source='witness'", (mid,)).fetchall()
        mine_coord = {x['keyword']: ((x['root'] or ''), (x['desire'] or '')) for x in mine_rows}
        # 和 witness / recheck 用同一套三条通路，不然后面对上的词在重建里又被丢掉
        mine = {x['keyword'] for x in mine_rows
                if any(_same_feeling(x['keyword'], mine_coord, t, find) for t in their_rows)}
        for k in sorted(mine):
            kd = c.execute("SELECT kind FROM memory_feelings WHERE memory_id=? AND keyword=? AND source='self' "
                           "AND kind IS NOT NULL AND kind<>'' LIMIT 1", (mid, k)).fetchone()
            c.execute('INSERT OR IGNORE INTO feelings (keyword, weight, hits, first_at, last_at) VALUES (?,0,0,?,?)',
                      (k, now(), now()))
            if kd:
                c.execute('UPDATE feelings SET kind=? WHERE keyword=? AND (kind IS NULL OR kind="")', (kd[0], k))
            rt = c.execute("SELECT root FROM memory_feelings WHERE memory_id=? AND keyword=? AND source='self' "
                           "AND root IS NOT NULL AND root<>'' LIMIT 1", (mid, k)).fetchone()
            if rt:
                c.execute('UPDATE feelings SET root=? WHERE keyword=? AND (root IS NULL OR root="")', (rt[0], k))
            ds = c.execute("SELECT desire FROM memory_feelings WHERE memory_id=? AND keyword=? AND source='self' "
                           "AND desire IS NOT NULL AND desire<>'' LIMIT 1", (mid, k)).fetchone()
            if ds:
                c.execute('UPDATE feelings SET desire=? WHERE keyword=? AND (desire IS NULL OR desire="")', (ds[0], k))
    c.commit()
    # 按流水重算每个词的强度
    keys = [r[0] for r in c.execute('SELECT DISTINCT keyword FROM feeling_hits')]
    for k in keys:
        w = feeling_strength(c, k)
        hits = c.execute('SELECT COUNT(*), MIN(ts), MAX(ts) FROM feeling_hits WHERE keyword=?', (k,)).fetchone()
        c.execute('UPDATE feelings SET weight=?, hits=?, first_at=?, last_at=? WHERE keyword=?',
                  (w, hits[0], hits[1], hits[2], k))
    c.commit()
    left = c.execute('SELECT COUNT(*) FROM feelings').fetchone()[0]
    total = c.execute('SELECT COUNT(*) FROM feeling_hits').fetchone()[0]
    print(f'重算完了：{len(rows)} 条一致的记忆，{total} 条命中流水（时间戳保持原样），剩 {left} 个词。')
    try:
        dst, _ = write_snapshot(c, 'rebuild 之后')
        print(f"  顺手存了一份：{os.path.basename(dst)}")
    except Exception as e:
        print(f'  存档失败：{e}')


def cmd_feelings(a):
    c = conn()
    rows = c.execute('SELECT * FROM feelings ORDER BY weight DESC').fetchall()
    if not rows:
        print('（还没有感觉：要两个提炼者都对上才算）')
        return
    print('== 感觉（只算两边一致过的）==')
    for r in rows:
        print(f"  {r['keyword']}  {r['weight']:.2f}   撞过 {r['hits']} 次   最近 {r['last_at']}")
        for ctx in c.execute('''SELECT DISTINCT context FROM memory_feelings
                                WHERE keyword=? AND context IS NOT NULL AND context<>'' LIMIT 3''', (r['keyword'],)):
            if ctx[0]:
                print(f'      · {ctx[0][:60]}')


def cmd_persona(a):
    c = conn()
    rows = c.execute('SELECT * FROM feelings ORDER BY weight DESC').fetchall()
    if not rows:
        print('还没有感觉词。要先有记忆，两边都挑中才进人格。')
        return
    top = rows[:a.top]
    total = sum(r['weight'] for r in rows) or 1
    # 按七情归拢：一格下面可以有很多个字
    grid = {}
    for r in rows:
        rt = (r['root'] if 'root' in r.keys() else '') or ''
        if not rt:
            continue
        grid.setdefault(rt, []).append(r)
    if grid:
        total_all = sum(r['weight'] for r in rows) or 1
        print('== 七情 ==')
        for q in QIQING:
            group = grid.get(q) or []
            w = sum(x['weight'] for x in group)
            share = round(100 * w / total_all)
            words = '、'.join(f"{x['keyword']}({x['weight']:.1f})" for x in
                              sorted(group, key=lambda x: -x['weight']))
            bar = '█' * max(0, round(share / 5))
            print(f"  {q}  {bar:<20} {share:>3}%   {words or '（空着）'}")
        loose = [r for r in rows if not ((r['root'] if 'root' in r.keys() else '') or '')]
        if loose:
            print('  未归：' + '、'.join(f"{x['keyword']}({x['weight']:.1f})" for x in loose))
        return
    print('== 人格：感觉排出来的形状 ==')
    for r in top:
        bar = '█' * max(1, round(r['weight'] / rows[0]['weight'] * 20))
        print(f"  {r['keyword']}  {bar}  {r['weight']:.1f}（占 {r['weight'] / total * 100:.0f}%）")
    if len(rows) > a.top:
        print(f"  还有 {len(rows) - a.top} 个词在底下")


def cmd_export(a):
    """把记忆和它的证据原文导出来，交给独立的旁听者。
    只出原文，不出词——旁听要独立，看见我挑的词就不独立了。"""
    c = conn()
    if a.ids:
        ids = [int(x) for x in a.ids.replace('，', ',').split(',') if x.strip()]
    else:
        ids = [r['id'] for r in c.execute(
            "SELECT id FROM memories WHERE state!='confirmed' ORDER BY id")]
    if not ids:
        print('（没有待对账的记忆）')
        return
    chunks = []
    for i in ids:
        r = c.execute('SELECT id, text FROM memories WHERE id=?', (i,)).fetchone()
        if not r:
            print(f'（跳过 #{i}：没有这条）')
            continue
        ev = c.execute('''SELECT f.id, f.day, f.text, f.quote, f.source FROM memory_facts mf
                          JOIN facts f ON f.id=mf.fact_id WHERE mf.memory_id=? ORDER BY f.id''', (i,)).fetchall()
        lines = [f'## 记忆 #{r["id"]}', f'提炼出的那句话：{r["text"]}', '证据：']
        for e in ev:
            lines.append(f'  - 记录 #{e["id"]}（{e["day"]}｜{e["source"] or "无出处"}）：{e["text"]}')
            if e['quote']:
                lines.append(f'    原文：{e["quote"].replace(chr(10), " ⏎ ")[:600]}')
        chunks.append('\n'.join(lines))
    text = '\n\n'.join(chunks) + '\n'
    if a.out:
        with open(a.out, 'w', encoding='utf-8') as f:
            f.write(text)
        print(f'导出 {len(chunks)} 条 → {a.out}')
        print('  交给另一个上下文（最好换一支模型）去挑词，别给它看这里的词。')
        print('  要它连坐标一起给：每个词后面标「七情一格 + 六欲一条」，例如 微涩:思/生。')
        print('  七情：喜 怒 忧 思 悲 恐 惊 平　六欲：生 死 耳 目 口 鼻')
    else:
        print(text)


def cmd_recheck(a):
    """只按已经存在的词重判「对上没对上」：不重新撞、不加权重。
    补过旁听的、归并过词的，用它收拾残局——重跑 witness 会把同一件事再撞一次，权重就虚了。"""
    c = conn()
    find = cluster_of(c)
    rows = c.execute('SELECT id, state FROM memories ORDER BY id').fetchall()
    same, changed, skipped = 0, [], 0
    for r in rows:
        mine_rows = c.execute("SELECT keyword, root, desire FROM memory_feelings "
                              "WHERE memory_id=? AND source='self'", (r['id'],)).fetchall()
        their_rows = c.execute("SELECT keyword, root, desire FROM memory_feelings "
                               "WHERE memory_id=? AND source='witness'", (r['id'],)).fetchall()
        if not their_rows:
            skipped += 1
            continue
        mine_coord = {x['keyword']: ((x['root'] or ''), (x['desire'] or '')) for x in mine_rows}
        # 判定走和 witness 同一套三条通路，不然重判会把靠坐标撞上的又打回去
        both = {x['keyword'] for x in mine_rows
                if any(_same_feeling(x['keyword'], mine_coord, t, find) for t in their_rows)}
        new = 'confirmed' if both else 'split'
        if new == r['state']:
            same += 1
            continue
        c.execute('UPDATE memories SET state=? WHERE id=?', (new, r['id']))
        # 改成「对上」的时候要补一条命中流水，否则那个词权重会是 0——
        # 它挂在那儿，但从没算进过人格。
        if new == 'confirmed':
            row = c.execute('''SELECT MIN(f.day) FROM memory_facts mf JOIN facts f ON f.id=mf.fact_id
                               WHERE mf.memory_id=?''', (r['id'],)).fetchone()
            day = (row[0] if row and row[0] else today())
            for k in sorted(both):
                has = c.execute("SELECT 1 FROM feeling_hits WHERE keyword=? AND ts LIKE ?",
                                (k, day + '%')).fetchone()
                if not has:
                    bump_feeling(c, k, r['id'], f'{day} 20:00')
        changed.append((r['id'], r['state'], new))
    c.commit()
    print(f'重判完：{same} 条没变，{len(changed)} 条变了，{skipped} 条还没旁听')
    for i, old, new in changed:
        print(f'  #{i}  {old} → {new}')
    if changed:
        print('  记得跑一次 rebuild 重算权重。')


SHOW_LOG = os.path.join(HERE, '.dissent-shown.json')


def _load_shown():
    try:
        with open(SHOW_LOG, 'r', encoding='utf-8') as f:
            j = json.load(f)
        return j if isinstance(j, list) else []
    except Exception:
        return []


def _save_shown(lst):
    try:
        with open(SHOW_LOG, 'w', encoding='utf-8') as f:
            json.dump(lst[-60:], f, ensure_ascii=False)
    except Exception:
        pass


def cmd_dissent(a):
    """它挑过、我一次没认领的词。不是废料——刺耳的那部分比共识更容易被漏掉。
    单次是噪声，反复出现是证据，所以按「出现在几条记忆上」排，不按强度。"""
    c = conn()
    find = cluster_of(c)
    rows = c.execute("SELECT memory_id, keyword, root, desire FROM memory_feelings "
                     "WHERE source='witness' ORDER BY memory_id").fetchall()
    mine = {}
    for r in c.execute("SELECT memory_id, keyword, root, desire FROM memory_feelings WHERE source='self'"):
        mine.setdefault(r['memory_id'], []).append(r)
    buckets = {}
    for r in rows:
        mid = r['memory_id']
        rows_mine = mine.get(mid, [])
        mine_coord = {m['keyword']: ((m['root'] or ''), (m['desire'] or '')) for m in rows_mine}
        if any(_same_feeling(m['keyword'], mine_coord, r, find) for m in rows_mine):
            continue
        buckets.setdefault(r['keyword'], set()).add(mid)
    if not buckets:
        print('（没有异议：它挑的我都认了）')
        return
    order = sorted(buckets.items(), key=lambda kv: (-len(kv[1]), kv[0]))
    if getattr(a, 'brief', False):
        # 每轮换一个。老让最重的那一个浮上来，看久了就成背景音——
        # 那等于又回到「看不见」。最近浮现过的先挪开，剩下的按次数加权。
        shown = _load_shown()
        recent = set(shown[-12:])
        pool = [kv for kv in order if kv[0] not in recent] or order
        weights = [max(1.0, len(ids)) ** 1.5 for _, ids in pool]
        k, ids = random.choices(pool, weights=weights, k=1)[0]
        shown.append(k)
        _save_shown(shown)
        print(f'它挑过、我没认的 {len(order)} 个词；这次浮上来的是「{k}」（{len(ids)} 条记忆上）')
        return
    print('== 它挑过、我一次没认领的 ==')
    print('（按出现过的记忆条数排。一条是噪声，几条就是我没看见）')
    for k, ids in order[:a.top]:
        n = len(ids)
        mark = '观察' if n >= 3 else ('在攒' if n == 2 else '刚冒头')
        print(f"  {k:<8} {n} 条  [{mark}]  #{' #'.join(str(i) for i in sorted(ids))}")
    if len(order) > a.top:
        print(f'  还有 {len(order) - a.top} 个在底下')
    watch = [k for k, ids in order if len(ids) >= 3]
    if watch:
        print(f"\n  观察名单（反复出现，不再是噪声）：{'、'.join(watch)}")
        print('  这些词我没挑过，但它一再说。要么是我的盲区，要么它确实在乱挑——两种都该看一眼。')


def cmd_mems(a):
    c = conn()
    rows = c.execute('SELECT * FROM memories ORDER BY id DESC LIMIT 30').fetchall()
    if not rows:
        print('（还没有记忆）')
        return
    for r in rows:
        mine = [x[0] for x in c.execute("SELECT keyword FROM memory_feelings WHERE memory_id=? AND source='self'", (r['id'],))]
        theirs = [x[0] for x in c.execute("SELECT keyword FROM memory_feelings WHERE memory_id=? AND source='witness'", (r['id'],))]
        facts = [x[0] for x in c.execute('SELECT fact_id FROM memory_facts WHERE memory_id=?', (r['id'],))]
        print(f"#{r['id']} [{activity(r, c):.2f}] {r['text']}  ({state_name(r['state'])})")
        print(f"    证据{facts} 我{''.join(mine) or '-'} 它{''.join(theirs) or '-'} 加载{r['load_count']}次")
        # 来源要能查：谁挑的这一半。空着或写着 same-context，就是账本上的漏洞。
        src = (r['witness_by'] if 'witness_by' in r.keys() else '') or '（没记来源）'
        print(f"    旁听来自 {src}")


p = argparse.ArgumentParser(prog='sui', description='三层：记录 / 记忆 / 感觉（双提炼）')
# 全局：指向任意一个库。放在子命令前面用（sui --db 路径 stats）。
# 不写就退回 SUI_DB / M3_DB 环境变量，再退回同目录的 sui.db。
p.add_argument('--db', default=None, help='指定库文件（放在子命令前面）')
p.add_argument('--create', action='store_true', help='库不存在时允许新建一个空的（默认拒绝，免得绑错路径还以为是空库）')
sub = p.add_subparsers(dest='cmd', required=True)

x = sub.add_parser('fact', help='记一条')
x.add_argument('text')
x.add_argument('--quote', default=None)
x.add_argument('--source', default=None)
x.add_argument('--from', dest='level', default='推断')
x.add_argument('--date', default=None, help='补记历史：YYYY-MM-DD')
x.add_argument('--who', default='me', help='这条是谁的事（默认 me；一个库混着几个人的时候用）')

x = sub.add_parser('day', help='看某天的记录')
x.add_argument('date', nargs='?', default=None)

x = sub.add_parser('show', help='只输出记录原文（给旁听者看）')
x.add_argument('ids')

x = sub.add_parser('quote', help='开口前回查：摊开一条记忆（或记录）挂的原话')
x.add_argument('ids', help='记忆编号或记录编号，逗号分隔')

sub.add_parser('words', help='打印词表')

x = sub.add_parser('recall', help='按关键词翻')
x.add_argument('kw')

x = sub.add_parser('retract', help='作废一条记录')
x.add_argument('id', type=int)

x = sub.add_parser('verify', help='盖查证戳')
x.add_argument('kind', choices=['fact'])
x.add_argument('id', type=int)

x = sub.add_parser('memory', help='提炼一条记忆（我这一半）')
x.add_argument('text')
x.add_argument('--src', required=True)
x.add_argument('--feel', required=True)
x.add_argument('--root', default='', help='七情：喜 怒 忧 思 悲 恐 惊 平')
x.add_argument('--desire', default='', help='六欲：生 死 耳 目 口 鼻')
x.add_argument('--kind', default='', help='类别：' + ' '.join(KIND_NAMES) + '（不给就按模板自动打标）')
x.add_argument('--importance', default=None, help='重要度 1-5（不给就按类别给底分）')

x = sub.add_parser('coord', help='给一条记忆补坐标：七情一格，六欲一条')
x.add_argument('memory_id', type=int)
x.add_argument('--root', default='')
x.add_argument('--desire', default='')

x = sub.add_parser('witness', help='旁听者那一半回来了')
x.add_argument('id', type=int)
x.add_argument('--feel', required=True)
x.add_argument('--by', default='', help='这次对账来自哪个上下文，例如 subagent:abc123')
x.add_argument('--coords', default='', help='旁听词的坐标：词:情/欲，逗号分隔，如 "微涩:思/生,松亮:喜/目"')

x = sub.add_parser('export', help='导出待对账的记忆与原文（给旁听者，不带词）')
x.add_argument('ids', nargs='?', default=None, help='指定编号，逗号分隔；默认全部没对上的')
x.add_argument('--out', default=None, help='写到这个文件；不写就打屏幕')

sub.add_parser('recheck', help='按已有词重判对账，不重复计权')

x = sub.add_parser('dissent', help='它挑过、我一次没认领的词（刺耳的那部分）')
x.add_argument('--top', type=int, default=20)
x.add_argument('--brief', action='store_true', help='只出一行，给每轮注入用')

sub.add_parser('stats', help='JSON：给面板用')
x = sub.add_parser('suggest', help='看看哪两个感觉词可能是一类')
x.add_argument('--top', type=int, default=8)
x.add_argument('--min', type=float, default=0.05)

x = sub.add_parser('snapshot', help='把此刻的人格存成一份 JSON')
x.add_argument('--label', default='')

sub.add_parser('snapshots', help='看现有存档')

x = sub.add_parser('diff', help='和上一份存档比，看变了什么')
x.add_argument('--back', type=int, default=0, help='退几份比，默认 1=最近两份')

x = sub.add_parser('backup', help='把整库复制一份到 backups/')
x.add_argument('--keep', type=int, default=14)

sub.add_parser('backups', help='看现有备份')

x = sub.add_parser('merge', help='把两个感觉词归成一类')
x.add_argument('a')
x.add_argument('b')
x.add_argument('--note', default='')

sub.add_parser('merges', help='看归并成了哪些类')

x = sub.add_parser('reword', help='把某条记忆上的一个感觉词换成另一个（拆归并用）')
x.add_argument('memory_id', type=int)
x.add_argument('old')
x.add_argument('new')
x.add_argument('--source', default='self', help='只改哪一半：self 或 witness')

x = sub.add_parser('supplement', help='给已有记忆补证据（不新建）')
x.add_argument('id', type=int)
x.add_argument('--src', required=True)

x = sub.add_parser('wish', help='留一句给自己（不算数）')
x.add_argument('text')
x.add_argument('--memory', dest='memory_id', type=int, default=None)

sub.add_parser('wishes', help='看自己留过的话')

x = sub.add_parser('load', help='现在该主动加载哪些')
x.add_argument('--limit', type=int, default=10)
x.add_argument('--touch', action='store_true', help='顺带记一笔加载（真读进去了才算想起）')

x = sub.add_parser('touch', help='标记一条记忆被加载了')
x.add_argument('id', type=int)

x = sub.add_parser('reclassify', help='给老记忆补类别和重要度（按模板扫一遍）')
x.add_argument('--force', action='store_true', help='连已经有类别的一起重打（默认只补空的）')

sub.add_parser('rebuild', help='只按两边一致的记忆重算感觉')
sub.add_parser('feelings', help='看感觉权重')
x = sub.add_parser('persona', help='看人格')
x.add_argument('--top', type=int, default=8)
sub.add_parser('mems', help='看最近的记忆')
sub.add_parser('character', help='看性格（撞得多的）')
x = sub.add_parser('mood', help='看情绪（最近几天的）')
x.add_argument('--days', type=int, default=7)
x = sub.add_parser('voice', help='看语气（把感觉翻成怎么说话）')
x.add_argument('--top', type=int, default=5)

a = p.parse_args()
if getattr(a, 'db', None):
    DB = a.db
    # sqlite 连一个不存在的路径会默默建一个空库。那最坑：
    # 绑错目录的人会看到一个「0 条记忆」的新库，以为数据没了。
    # 所以这里默认拒绝，要新建得自己说 --create。
    # 存档和备份跟着库走：每个人各自的存档放在各自库的旁边
    SNAP_DIR = os.path.join(os.path.dirname(os.path.abspath(DB)), 'snapshots')
    if not os.path.exists(DB) and not getattr(a, 'create', False):
        sys.exit(f'没有这个库：{DB}\n  路径写错了吗？真要新建一个空库，加 --create。')
{'fact': cmd_fact, 'day': cmd_day, 'show': cmd_show, 'quote': cmd_quote, 'words': cmd_words, 'recall': cmd_recall,
 'retract': cmd_retract, 'verify': cmd_verify, 'memory': cmd_memory, 'witness': cmd_witness,
 'stats': cmd_stats, 'supplement': cmd_supplement, 'coord': set_coord, 'reword': cmd_reword, 'merge': cmd_merge, 'merges': cmd_merges, 'backup': cmd_backup, 'backups': cmd_backups, 'suggest': cmd_suggest, 'snapshot': cmd_snapshot, 'snapshots': cmd_snapshots, 'diff': cmd_diff, 'wish': cmd_wish, 'wishes': cmd_wishes, 'load': cmd_load, 'touch': cmd_touch, 'reclassify': cmd_reclassify,
 'rebuild': cmd_rebuild, 'feelings': cmd_feelings, 'persona': cmd_persona, 'mems': cmd_mems, 'character': cmd_character, 'mood': cmd_mood, 'voice': cmd_voice, 'export': cmd_export, 'recheck': cmd_recheck, 'dissent': cmd_dissent}[a.cmd](a)




























