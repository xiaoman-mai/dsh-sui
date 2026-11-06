#!/usr/bin/env node
// 插件层契约测试：不启宿主，只验「工具怎么调」和「命令行有没有这个子命令」对得上。
// 数据层的规矩（活跃度、对账、归并）在 tools/sui/test_sui.py 里跑。
//
//   node dsh-sui/test/contract.mjs
//
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const here = path.dirname(fileURLToPath(import.meta.url))
const pkgDir = path.resolve(here, '..')
const repo = path.resolve(pkgDir, '..')
const indexFile = path.join(pkgDir, 'lib', 'index.mjs')
const pyFile = path.join(repo, 'tools', 'sui', 'sui.py')

let failures = 0
function ok(msg) { console.log('  ok   ' + msg) }
function bad(msg) { failures++; console.log('  FAIL ' + msg) }
function check(cond, msg) { cond ? ok(msg) : bad(msg) }

console.log('1. 包结构')
const pkg = JSON.parse(fs.readFileSync(path.join(pkgDir, 'package.json'), 'utf8'))
for (const f of ['lib/index.mjs', 'lib/client.js', 'cordis.patch.yml', 'README.md', 'LICENSE']) {
  check(fs.existsSync(path.join(pkgDir, f)), f + ' 在')
}
check(pkg.name === 'dsh-sui', '包名 dsh-sui')
check(pkg.dsh && pkg.dsh.bundle && pkg.dsh.bundle.patch === './cordis.patch.yml', 'bundle patch 指对了')
for (const exp of Object.values(pkg.exports || {})) {
  if (typeof exp !== 'string' || exp.includes('*')) continue
  check(fs.existsSync(path.join(pkgDir, exp)), 'exports ' + exp + ' 存在')
}

console.log('2. 命令行子命令')
const py = fs.readFileSync(pyFile, 'utf8')
const cmds = new Set([...py.matchAll(/add_parser\('([a-z_]+)'/g)].map(m => m[1]))
check(cmds.size >= 25, `sui.py 有 ${cmds.size} 个子命令`)
for (const must of ['fact', 'memory', 'witness', 'load', 'touch', 'voice', 'rebuild', 'stats']) {
  check(cmds.has(must), '子命令 ' + must)
}

console.log('3. 工具 ↔ 子命令')
const src = fs.readFileSync(indexFile, 'utf8')
const blocks = src.split(/\n\s{2}reg\(\{/).slice(1)
check(blocks.length >= 28, `注册了 ${blocks.length} 个工具`)

const seen = new Set()
for (const b of blocks) {
  const nameM = b.match(/name:\s*'(sui_[a-z_]+)'/)
  if (!nameM) { bad('有一块 reg 没取到工具名'); continue }
  const name = nameM[1]
  if (seen.has(name)) bad('工具名重复：' + name)
  seen.add(name)
  // run( 之后的第一个字符串，就是它真正敲的命令
  const call = b.match(/run\(\s*(?:args\.[^\n]*?\?\s*)?\[?[^\n]*?['"]([a-z_]+)['"]/)
  const cmd = call ? call[1] : (b.match(/run\(\[([^\]]*)\]/) || [])[1]
  if (!cmd || typeof cmd !== 'string' || /^[A-Z]/.test(cmd)) {
    // 少数工具用变量拼参数，跳过但记一笔
    ok(name + ' → （动态参数，跳过比对）')
    continue
  }
  check(cmds.has(cmd), `${name} → ${cmd}`)
}
check(seen.size >= 28, `共 ${seen.size} 个不同工具名`)

console.log('4. 必备工具都在')
for (const must of ['sui_fact', 'sui_memory', 'sui_witness', 'sui_load', 'sui_voice', 'sui_persona']) {
  check(seen.has(must), must)
}

console.log('5. 语气表只有一份')
const pyTone = (py.match(/^TONE = \{/gm) || []).length
check(pyTone === 1, `sui.py 里 TONE 定义 ${pyTone} 处`)
check(!/tone = \{\s*'暖'/.test(py), '没有第二份手写语气表')
check(!/rules = \{\s*'急'/.test(py), '没有第二份手写语气表（rules）')

console.log('')
if (failures) {
  console.log(`失败 ${failures} 项`)
  process.exit(1)
}
console.log('ALL PASS')
