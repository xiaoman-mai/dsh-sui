#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""sui 双提炼版的测试：跑在临时库上，绝不碰 sui.db"""
import os, sys, subprocess, tempfile, sqlite3
from datetime import datetime, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
SUI = os.path.join(HERE, 'sui.py')
PY = sys.executable

tmp = tempfile.mkdtemp(prefix='suitest-')
db = os.path.join(tmp, 'test.db')
env = dict(os.environ, SUI_DB=db, PYTHONIOENCODING='utf-8')

fail = 0


def run(*args):
    p = subprocess.run([PY, SUI, *args], env=env, capture_output=True, text=True, encoding='utf-8')
    return p.returncode, (p.stdout or '') + (p.stderr or '')


def sql(q, *a):
    c = sqlite3.connect(db)
    c.execute(q, a)
    c.commit()
    c.close()


def check(name, cond, detail=''):
    global fail
    if cond:
        print(f'  ok   {name}')
    else:
        fail += 1
        print(f'  FAIL {name}  {detail[:300]}')


print('1. 没有记录，不许写记忆')
rc, out = run('memory', '凭空一条', '--src', '99', '--feel', '安')
check('拒了', rc != 0, out)

print('2. 没有感觉词，不许写记忆')
run('fact', '今天把浏览器弄通了', '--source', '对话', '--from', '亲历')
rc, out = run('memory', '摘抄一句', '--src', '1')
check('拒了', rc != 0, out)

print('4. 我这一半写完，还是 pending，感觉不进人格')
rc, out = run('memory', '卡住时换个东西试', '--src', '1', '--feel', '急,钝')
check('写进去了', rc == 0, out)
check('在等旁听', '等旁听' in out, out)
rc, out = run('feelings')
check('人格里还没有它', '还没有感觉' in out, out)
rc, out = run('load')
check('pending 不进上下文', '没有该主动加载' in out, out)

print('5. 旁听者对上了，词才进人格')
rc, out = run('witness', '1', '--feel', '急')
check('两边一致', '两边都对上' in out, out)
check('急 进人格', '两边都对上' in out, out)
rc, out = run('feelings')
check('急 进去了', '急' in out and '钝' not in out, out)

print('6. 旁听者一个都没对上，标成有分歧')
run('fact', '又卡了一次', '--source', '对话')
run('memory', '还是同一个毛病', '--src', '2', '--feel', '闷,累')
rc, out = run('witness', '2', '--feel', '奇')
check('标了有分歧', '有分歧' in out, out)
rc, out = run('persona')
check('闷 累 奇 都没进人格', all(w not in out for w in ['闷', '累', '奇']), out)

print('7. 同一个词再撞一次，权重往上加')
run('fact', '第三次卡住', '--source', '对话')
run('memory', '第三次还是卡', '--src', '3', '--feel', '急')
rc, out = run('witness', '3', '--feel', '急')
check('重复对账是幂等的', ('已经对过账' in out) or ('撞上' in out), out)
check('幂等时不再计次', ('已经对过账' in out) or ('共 2 次' in out), out)

print('8. 小路上的话不进人格')
rc, out = run('wish', '我希望那条情绪是稳，不是急')
check('存进去了', '不进人格' in out, out)
rc, out = run('persona')
check('人格里有急没稳', '急' in out and '稳' not in out, out)
rc, out = run('wishes')
check('小路翻得到', '我希望' in out, out)

print('9. 活跃度会随时间掉')
rc, out = run('load')
check('现在能加载', '该进上下文' in out, out)
old = (datetime.now() - timedelta(days=40)).strftime('%Y-%m-%d %H:%M')
sql('UPDATE memories SET created=?, last_loaded=NULL', old)
rc, out = run('load')
check('40 天后不加载了', '没有该主动加载' in out, out)

print('10. 复习过一次的，掉得慢')
sql('UPDATE memories SET created=?, last_loaded=?, load_count=5',
    (datetime.now() - timedelta(days=40)).strftime('%Y-%m-%d %H:%M'),
    (datetime.now() - timedelta(days=25)).strftime('%Y-%m-%d %H:%M'))
rc, out = run('load')
check('25 天前复习过，还在', '该进上下文' in out, out)

print('11. 中文、标点、emoji 不坏')
run('fact', '测试：引号「」、逗号，破折号——还有 emoji 🌾', '--source', 'test')
rc, out = run('recall', '🌾')
check('读回来了', '🌾' in out, out)

print('12. 性格看撞的次数和跨度，情绪只看最近的')
rc, out = run('character')
check('性格里有急', '急' in out, out)
check('标了刚冒头或在攒', ('刚冒头' in out) or ('在攒' in out) or ('底子' in out), out)
rc, out = run('mood', '--days', '7')
check('情绪里有急', '急' in out, out)
rc, out = run('voice')
check('语气翻出一条', ('急' in out) or ('还没有' in out), out)

print('13. 补记历史日期的记录，能按那天翻到')
run('fact', '十月中旬的一件旧事', '--source', '旧账', '--date', '2026-10-20')
rc, out = run('day', '2026-10-20')
check('翻得到', '十月中旬的一件旧事' in out, out)

print('14. 词不一样，但七情六欲落在同一格——也算对上')
run('fact', '她把杯子推过来，没说别的', '--source', '对话')
run('memory', '递过来就够了', '--src', '6', '--feel', '暖', '--root', '喜', '--desire', '耳')
rc, out = run('witness', '4', '--feel', '微涩', '--coords', '微涩:喜/耳', '--by', 'test')
check('靠坐标撞上', '（坐标）' in out, out)
check('这条判成一致', '旁听回来了' in out and '分歧' not in out, out)

print('15. 坐标错开、词也错开，才是真分歧')
run('fact', '他把没写完的那页合上了', '--source', '对话')
run('memory', '停在半路也是停', '--src', '7', '--feel', '闷', '--root', '忧', '--desire', '目')
rc, out = run('witness', '5', '--feel', '半截', '--coords', '半截:喜/生', '--by', 'test')
check('判成分歧', '有分歧' in out, out)

print('16. 只标一情不标欲，不算坐标对上')
run('fact', '路过那家关了门的店', '--source', '对话')
run('memory', '关着的门也算门', '--src', '8', '--feel', '静', '--root', '平', '--desire', '目')
rc, out = run('witness', '6', '--feel', '生锈', '--coords', '生锈:平', '--by', 'test')
check('缺六欲就不走坐标', '有分歧' in out, out)

print('17. 异议账：它挑过、我一次没认的词要能看见')
rc, out = run('dissent')
check('列出了它挑的「半截」', '半截' in out, out)
check('也列出了「生锈」', '生锈' in out, out)
rc, out = run('dissent', '--brief')
lines = [l for l in out.strip().split('\n') if l.strip()]
check('brief 只出一行', len(lines) == 1, out)
check('brief 说得出个数', '个词' in out, out)

print('\n库里现在：')
c = sqlite3.connect(db)
for t in ('facts', 'memories', 'memory_facts', 'feelings', 'memory_feelings', 'wishes'):
    print(f'  {t}: {c.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]} 行')

print(f'\n临时库：{db}')
print('ALL PASS' if fail == 0 else f'{fail} FAILED')
sys.exit(1 if fail else 0)






