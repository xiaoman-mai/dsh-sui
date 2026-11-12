// ============================================================================
// dsh-sui ·「穗」—— client half（浏览器 bundle）
// 三层记忆的面板：记录 / 记忆 / 感觉，外加此刻的语气。
// 用 React.createElement，不用 jsxs —— jsxs 的第三个参数是 key，不是 children。
// ============================================================================
window.__ModuleLoader__.load({
	id: 'dsh-sui',
	factory(require) {
		const React = require('react');
		const h = React.createElement;

		const PANEL_ID = 'sui';
		const TITLE = '穗 · sui';

		const CSS = [
			'.sui-root{height:100%;min-height:0;overflow-y:auto;box-sizing:border-box;scrollbar-width:thin;}',
			'.sui-root::-webkit-scrollbar{width:9px;}',
			'.sui-root::-webkit-scrollbar-thumb{background:var(--dsw-alias-border-l2,rgba(255,255,255,.22));border-radius:5px;}',
			'.sui-inner{max-width:820px;margin:0 auto;padding:26px 22px 56px;display:flex;flex-direction:column;gap:18px;}',
			'.sui-head{display:flex;align-items:baseline;gap:10px;flex-wrap:wrap;}',
			'.sui-title{font-size:17px;font-weight:600;color:var(--dsw-alias-label-primary,#e8eaf0);}',
			'.sui-sub{font-size:12px;color:var(--dsw-alias-label-secondary,rgba(232,234,240,.5));}',
			'.sui-cards{display:flex;gap:10px;flex-wrap:wrap;}',
			'.sui-card{flex:1;min-width:110px;border:1px solid var(--dsw-alias-border-l1,rgba(255,255,255,.09));border-radius:10px;padding:10px 13px;background:var(--dsw-alias-bg-layer-1,rgba(255,255,255,.025));}',
			'.sui-card .k{font-size:11px;color:var(--dsw-alias-label-secondary,rgba(232,234,240,.5));}',
			'.sui-card .v{font-size:20px;font-weight:600;color:var(--dsw-alias-label-primary,#e8eaf0);margin-top:2px;}',
			'.sui-card .n{font-size:11px;color:var(--dsw-alias-label-secondary,rgba(232,234,240,.45));margin-top:2px;}',
			'.sui-sec{display:flex;flex-direction:column;gap:8px;}',
			'.sui-sec-h{font-size:12px;font-weight:600;letter-spacing:.04em;color:var(--dsw-alias-label-secondary,rgba(232,234,240,.72));}',
			'.sui-bar{display:flex;align-items:center;gap:10px;font-size:13px;}',
			'.sui-bar .w{width:2.4em;text-align:center;font-weight:600;color:var(--dsw-alias-label-primary,#e8eaf0);}',
			'.sui-bar .t{flex:1;height:7px;border-radius:4px;background:var(--dsw-alias-bg-layer-2,rgba(255,255,255,.07));overflow:hidden;}',
			'.sui-bar .f{height:100%;border-radius:4px;background:var(--dsw-alias-brand-primary,rgba(126,184,255,.9));}',
			'.sui-bar .p{width:3em;text-align:right;font-size:11px;color:var(--dsw-alias-label-secondary,rgba(232,234,240,.5));}',
			'.sui-bar .m{width:5.2em;font-size:11px;color:var(--dsw-alias-label-secondary,rgba(232,234,240,.45));}',
			'.sui-mem{display:flex;gap:9px;align-items:flex-start;font-size:13px;line-height:1.5;}',
			'.sui-mem .id{width:2.6em;flex:none;font-size:11px;color:var(--dsw-alias-label-secondary,rgba(232,234,240,.4));padding-top:2px;}',
			'.sui-mem .tx{flex:1;color:var(--dsw-alias-label-primary,rgba(232,234,240,.85));}',
			'.sui-mem .sui-wd{font-size:11px !important;line-height:16px !important;color:var(--dsw-alias-brand-primary,rgba(126,184,255,.85));margin-left:6px;display:inline-block;font-weight:400 !important;}',
			'.sui-tag{display:inline-block;font-size:10px;padding:1px 6px;border-radius:999px;border:1px solid;margin-left:6px;}',
			'.sui-tag.ok{color:var(--dsw-alias-state-success-primary,rgba(126,220,160,.9));border-color:var(--dsw-alias-state-success-primary,rgba(126,220,160,.35));}',
			'.sui-tag.split{color:var(--dsw-alias-state-warn-primary,rgba(230,180,110,.9));border-color:var(--dsw-alias-state-warn-primary,rgba(230,180,110,.35));}',
			'.sui-tag.pend{color:var(--dsw-alias-label-secondary,rgba(200,200,210,.7));border-color:var(--dsw-alias-border-l1,rgba(200,200,210,.25));}',
			'.sui-empty{font-size:12px;color:var(--dsw-alias-label-secondary,rgba(232,234,240,.45));}',
			'.sui-foot{font-size:11px;color:var(--dsw-alias-label-secondary,rgba(232,234,240,.35));}',
		].join('\n');

		const STATE_TEXT = { confirmed: '对上', split: '有分歧', pending: '等旁听' };
		const STATE_CLASS = { confirmed: 'ok', split: 'split', pending: 'pend' };

		// 一枝麦穗：五粒，一根茎。粒是记录，穗是记忆。
		function WheatIcon(props) {
			const size = (props && props.size) || 16;
			const grain = function (key, cx, cy, rot) {
				return h('ellipse', {
					key: key, cx: cx, cy: cy, rx: 1.35, ry: 2.05,
					transform: 'rotate(' + rot + ' ' + cx + ' ' + cy + ')',
				});
			};
			return h('svg', {
				width: size, height: size, viewBox: '0 0 16 16', fill: 'none',
				stroke: 'currentColor', strokeWidth: 1.2, strokeLinecap: 'round', strokeLinejoin: 'round',
			},
				h('path', { key: 's', d: 'M8 14.2V4.4' }),
				grain('g1', 6.1, 6.2, -28),
				grain('g2', 9.9, 6.2, 28),
				grain('g3', 6.1, 9.4, -24),
				grain('g4', 9.9, 9.4, 24),
				grain('g5', 8, 3.6, 0),
			);
		}

		function Bar(props) {
			const ctx = props.contexts && props.contexts.length ? props.contexts[0] : '';
			// 性格不看此刻多重，看撞了几次、跨了多少天
			const hits = props.hits || 0;
			const span = props.spanDays || 0;
			const mark = (hits >= 3 && span >= 7) ? '底子' : (hits >= 2 ? '在攒' : '刚冒头');
			const mc = mark === '底子'
				? 'var(--dsw-alias-state-success-primary, #7edca0)'
				: (mark === '在攒'
					? 'var(--dsw-alias-state-warn-primary, #e6b46e)'
					: 'var(--dsw-alias-label-secondary, rgba(200,200,210,.7))');
			return h('div', { className: 'sui-sec', style: { gap: 2 } },
				h('div', { className: 'sui-bar' },
					h('div', { className: 'w' }, props.keyword),
					h('div', { className: 't' },
						h('div', { className: 'f', style: { width: Math.max(3, props.share || 0) + '%' } })),
					h('div', { className: 'p' }, (props.share || 0) + '%'),
					h('div', { className: 'm', style: { width: '3em' } }, props.weight.toFixed(2)),
					h('div', {
						style: { fontSize: 11, width: '7.2em', color: mc, whiteSpace: 'nowrap' },
					}, '撞' + hits + ' · 跨' + Math.round(span) + '天'),
					h('div', {
						style: {
							fontSize: 10, padding: '1px 6px', borderRadius: 4, color: mc,
							border: '1px solid ' + mc, whiteSpace: 'nowrap',
						},
					}, mark)
				),
				ctx ? h('div', {
					style: {
						fontSize: 11, paddingLeft: 34, opacity: .55,
						color: 'var(--dsw-alias-label-secondary)',
						whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis',
					},
				}, '“' + ctx + '”') : null
			);
		}

		function Card(label, value, note) {
			return h('div', { className: 'sui-card' },
				h('div', { className: 'k' }, label),
				h('div', { className: 'v' }, String(value)),
				h('div', { className: 'n' }, note)
			);
		}


		function Field(props) {
			return h('label', {
				style: { display: 'flex', alignItems: 'center', gap: 8, fontSize: 12, color: 'var(--dsw-alias-label-secondary, rgba(232,234,240,.7))' },
			},
				h('span', { style: { minWidth: 96, opacity: .8 } }, props.label),
				h('input', {
					type: 'number',
					value: props.value,
					min: props.min,
					max: props.max,
					step: props.step === undefined ? 1 : props.step,
					onChange: function (e) { props.onChange(Number(e.target.value)) },
					style: {
						width: 72, padding: '3px 6px', borderRadius: 6, fontSize: 12,
						background: 'var(--dsw-alias-bg-layer-2, rgba(255,255,255,.06))', color: 'var(--dsw-alias-label-primary, inherit)',
						border: '1px solid var(--dsw-alias-border-l2, rgba(255,255,255,.14))', outline: 'none',
					},
				}),
				h('span', { style: { opacity: .55, fontSize: 11, color: 'var(--dsw-alias-label-secondary)' } }, props.hint || ''),
			);
		}

		function Settings(props) {
			const st = React.useState(null);
			const cur = st[0];
			const setCur = st[1];
			const note = React.useState('');
			const setNote = note[1];

			React.useEffect(function () {
				fetch('/sui/settings' + (props.viewDb ? '?db=' + encodeURIComponent(props.viewDb) : ''), { cache: 'no-store' })
					.then(function (r) { return r.json(); })
					.then(function (j) { if (j && j.ok) setCur(j.settings); })
					.catch(function () { });
			}, []);

			if (!cur) return null;

			const set = function (k, v) {
				const next = Object.assign({}, cur);
				next[k] = v;
				setCur(next);
			};
			const save = function () {
				fetch('/sui/settings' + (props.viewDb ? '?db=' + encodeURIComponent(props.viewDb) : ''), {
					method: 'POST',
					headers: { 'content-type': 'application/json' },
					body: JSON.stringify(cur),
				}).then(function (r) { return r.json(); })
					.then(function (j) {
						setNote(j && j.ok ? '存好了，下一分钟生效' : '没存上');
						setTimeout(function () { setNote(''); }, 2500);
					})
					.catch(function () { setNote('没存上'); });
			};

			return h('div', { className: 'sui-sec', style: { marginTop: 8 } },
				h('div', { className: 'sui-sec-h' }, '参数'),
				h('div', { style: { display: 'flex', flexDirection: 'column', gap: 6 } },
					h(Field, { label: '轻提一句', value: cur.pressureMid, min: 10, max: 95, hint: '上下文到这个百分比', onChange: function (v) { set('pressureMid', v) } }),
					h(Field, { label: '自动落盘', value: cur.pressureHigh, min: 20, max: 99, hint: '到这个百分比就自己记', onChange: function (v) { set('pressureHigh', v) } }),
					h(Field, { label: '每轮带几条', value: cur.recallItems, min: 0, max: 80, hint: '撑起一个记忆体要几十条', onChange: function (v) { set('recallItems', v) } }),
					h(Field, { label: '每轮带几个词', value: cur.voiceItems, min: 0, max: 12, onChange: function (v) { set('voiceItems', v) } }),
					h(Field, { label: '注入字数上限', value: cur.maxChars, min: 100, max: 8000, onChange: function (v) { set('maxChars', v) } }),
					h(Field, { label: '一次最多落几条', value: cur.autoRecordBatch, min: 1, max: 20, onChange: function (v) { set('autoRecordBatch', v) } }),
					h(Field, { label: '淡出阈值', value: cur.decayThreshold, min: 0, max: 5, step: 0.05, hint: '活跃度低于它就淡出', onChange: function (v) { set('decayThreshold', v) } }),
					h(Field, { label: '加载窗口', value: cur.loadWindowDays, min: 1, max: 365, hint: '天', onChange: function (v) { set('loadWindowDays', v) } }),
					h(Field, { label: '衰减系数', value: cur.decayPower, min: 0.1, max: 1.5, step: 0.05, hint: 'ACT-R 的 d', onChange: function (v) { set('decayPower', v) } }),
				),
				h('div', { style: { display: 'flex', alignItems: 'center', gap: 10, marginTop: 2 } },
					h('button', {
						onClick: function () {
							setNote('在重算…');
							fetch('/sui/rebuild' + (props.viewDb ? '?db=' + encodeURIComponent(props.viewDb) : ''), { method: 'POST' })
								.then(function (r) { return r.json(); })
								.then(function (j) { setNote(j && j.ok ? '重算完了' : '重算失败'); setTimeout(function () { setNote(''); }, 3000); })
								.catch(function () { setNote('重算失败'); });
						},
						style: {
							fontSize: 12, padding: '4px 14px', borderRadius: 6, cursor: 'pointer',
							background: 'var(--dsw-alias-bg-layer-2, rgba(255,255,255,.06))',
							color: 'var(--dsw-alias-label-primary)',
							border: '1px solid var(--dsw-alias-border-l2, rgba(255,255,255,.14))',
						},
					}, '重算权重'),
					h('button', {
						onClick: function () {
							setNote('在备份…');
							fetch('/sui/backup' + (props.viewDb ? '?db=' + encodeURIComponent(props.viewDb) : ''), { method: 'POST' })
								.then(function (r) { return r.json(); })
								.then(function (j) {
									setNote(j && j.ok ? (j.message || '备份好了') : '备份失败');
									setTimeout(function () { setNote(''); }, 4000);
								})
								.catch(function () { setNote('备份失败'); });
						},
						style: {
							fontSize: 12, padding: '4px 14px', borderRadius: 6, cursor: 'pointer',
							background: 'var(--dsw-alias-bg-layer-2, rgba(255,255,255,.06))',
							color: 'var(--dsw-alias-label-primary)',
							border: '1px solid var(--dsw-alias-border-l2, rgba(255,255,255,.14))',
						},
					}, '备份库'),
					h('button', {
						onClick: save,
						style: {
							fontSize: 12, padding: '4px 14px', borderRadius: 6, cursor: 'pointer',
							background: 'var(--dsw-alias-bg-layer-2, rgba(126,184,255,.16))', color: 'var(--dsw-alias-label-primary, rgba(200,225,255,.95))',
							border: '1px solid var(--dsw-alias-brand-primary, rgba(126,184,255,.35))',
						},
					}, '存一下'),
					note[0] ? h('span', { style: { fontSize: 11, opacity: .6 } }, note[0]) : null,
				),
			);
		}

		// ---- 人：谁、认哪些预设、账本在哪 ----
		const BTN = {
			fontSize: 12, padding: '4px 14px', borderRadius: 6, cursor: 'pointer', flex: 'none',
			background: 'var(--dsw-alias-bg-layer-2, rgba(255,255,255,.06))',
			color: 'var(--dsw-alias-label-primary)',
			border: '1px solid var(--dsw-alias-border-l2, rgba(255,255,255,.14))',
		};
		const INP = {
			fontSize: 12, padding: '5px 9px', borderRadius: 6, width: '100%', boxSizing: 'border-box',
			background: 'var(--dsw-alias-bg-layer-1, rgba(255,255,255,.03))',
			color: 'var(--dsw-alias-label-primary)',
			border: '1px solid var(--dsw-alias-border-l1, rgba(255,255,255,.1))',
		};

		function People(props) {
			const ds = React.useState(null); const data = ds[0]; const setData = ds[1];
			const fs2 = React.useState({ name: '', presets: '', workspace: '', db: '' });
			const form = fs2[0]; const setForm = fs2[1];
			const ns = React.useState(''); const note = ns[0]; const setNote = ns[1];

			function load() {
				fetch('/sui/people', { cache: 'no-store' })
					.then(function (r) { return r.json(); })
					.then(function (j) { setData(j); })
					.catch(function () { setData({ ok: false, error: '读不到' }); });
			}
			React.useEffect(load, []);

			function post(body) {
				return fetch('/sui/people', {
					method: 'POST',
					headers: { 'content-type': 'application/json' },
					body: JSON.stringify(body),
				}).then(function (r) { return r.json(); });
			}

			if (!data) return h('div', { className: 'sui-empty' }, '读中…');
			if (!data.ok) return h('div', { className: 'sui-empty' }, '读不到：' + (data.error || ''));

			const rows = (data.people || []).map(function (p) {
				return h('div', {
					key: p.name,
					style: {
						display: 'flex', gap: 10, alignItems: 'flex-start', padding: '8px 0',
						borderBottom: '1px solid var(--dsw-alias-border-l1, rgba(255,255,255,.06))',
					},
				},
					h('div', { style: { flex: 1, minWidth: 0 } },
						h('div', { style: { fontSize: 13 } }, p.name),
						h('div', { style: { fontSize: 11, opacity: .55, marginTop: 2 } },
							'预设 ' + ((p.presets && p.presets.length) ? p.presets.join('、') : '—')),
						h('div', { style: { fontSize: 11, opacity: .5, wordBreak: 'break-all', marginTop: 1 } },
							p.db || '还没给库'),
						h('div', { style: { fontSize: 11, opacity: .55, marginTop: 1 } },
							p.error ? p.error : ((p.memories === null ? '—' : p.memories) + ' 条记忆'))),
					h('div', { style: { display: 'flex', gap: 6, flex: 'none' } },
						h('button', {
							onClick: function () { if (props.onView) props.onView(p.db); },
							style: BTN,
						}, '看'),
						h('button', {
							onClick: function () { post({ name: p.name, remove: true }).then(load); },
							style: BTN,
						}, '删')));
			});

			function set(k, v) {
				setForm({ name: form.name, presets: form.presets, workspace: form.workspace, db: form.db, [k]: v });
			}

			return h('div', { className: 'sui-sec', style: { marginTop: 8 } },
				props.viewDb
					? h('div', { style: { display: 'flex', gap: 8, alignItems: 'center', marginBottom: 8 } },
						h('span', { style: { fontSize: 12, color: 'var(--dsw-alias-brand-primary, #7eb8ff)' } },
							'正在看：' + props.viewDb),
						h('button', { onClick: function () { if (props.onView) props.onView(''); }, style: BTN }, '回到默认'))
					: null,
				h('div', { className: 'sui-sec-h' }, '人'),
				rows.length
					? h('div', null, rows)
					: h('div', { className: 'sui-foot' }, '还没登记过人。没登记的会话，按工作区找自己目录下的 tools/sui/sui.db。'),
				h('div', { className: 'sui-sec-h', style: { marginTop: 12 } }, '新增 / 改一个人'),
				h('div', { style: { display: 'flex', flexDirection: 'column', gap: 6 } },
					h('input', { style: INP, placeholder: '名字，例如 小满', value: form.name, onChange: function (e) { set('name', e.target.value); } }),
					h('input', { style: INP, placeholder: '认哪些预设，逗号分隔，例如 daughter-agent,standard', value: form.presets, onChange: function (e) { set('presets', e.target.value); } }),
					h('input', { style: INP, placeholder: '工作区（可空）', value: form.workspace, onChange: function (e) { set('workspace', e.target.value); } }),
					h('input', { style: INP, placeholder: '库文件，例如 .../tools/sui/sui.db', value: form.db, onChange: function (e) { set('db', e.target.value); } }),
					h('div', { style: { display: 'flex', gap: 10, alignItems: 'center' } },
						h('button', {
							onClick: function () {
								if (!form.name.trim() || !form.db.trim()) { setNote('名字和库都要填'); return; }
								post({
									name: form.name.trim(),
									presets: form.presets,
									workspace: form.workspace.trim(),
									db: form.db.trim(),
								}).then(function (j) {
									setNote(j && j.ok ? '存好了' : ('没存上：' + ((j && j.error) || '')));
									if (j && j.ok) { setForm({ name: '', presets: '', workspace: '', db: '' }); load(); }
								}).catch(function () { setNote('没存上'); });
							},
							style: BTN,
						}, '保存'),
						note ? h('span', { style: { fontSize: 11, opacity: .6 } }, note) : null)),
			);
		}

		// 存档一块：自己带状态，不跟别的块抢
		function Snapshot(props) {
			const st = React.useState('');
			const note = st[0];
			const setNote = st[1];
			const list = props.data.snapshots || [];
			return h('div', { className: 'sui-sec' },
				h('div', { className: 'sui-sec-h' }, '存档'),
				h('div', { style: { display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' } },
					h('button', {
						onClick: function () {
							setNote('在存…');
							fetch('/sui/snapshot' + (props.viewDb ? '?db=' + encodeURIComponent(props.viewDb) : ''), { method: 'POST' })
								.then(function (r) { return r.json(); })
								.then(function (j) {
									setNote(j && j.ok ? '存好了' : '没存上');
									if (props.onSaved) props.onSaved();
									setTimeout(function () { setNote(''); }, 3000);
								})
								.catch(function () { setNote('没存上'); });
						},
						style: {
							fontSize: 12, padding: '4px 14px', borderRadius: 6, cursor: 'pointer',
							background: 'var(--dsw-alias-bg-layer-2, rgba(255,255,255,.06))',
							color: 'var(--dsw-alias-label-primary)',
							border: '1px solid var(--dsw-alias-border-l2, rgba(255,255,255,.14))',
						},
					}, '存一份'),
					note ? h('span', { style: { fontSize: 11, opacity: .6 } }, note) : null,
				),
				h('div', { className: 'sui-foot' },
					list.length ? '共 ' + list.length + ' 份' : '还没有存档'),
				list.length
					? h('div', { className: 'sui-sec', style: { gap: 4 } }, list.map(function (s, i) {
						return h('div', {
							key: 'snap' + i,
							style: {
								display: 'flex', gap: 10, fontSize: 11,
								color: 'var(--dsw-alias-label-secondary)', opacity: .75,
							},
						},
							h('span', { style: { width: 88, flex: 'none' } }, (s.at || '').slice(5)),
							h('span', { children: '记录 ' + s.facts + ' · 记忆 ' + s.memories }),
							s.top ? h('span', { children: '最强 ' + s.top }) : null,
							s.label ? h('span', { style: { opacity: .6 } }, '「' + s.label + '」') : null,
						);
					}))
					: null,
			);
		}

		function Tabs(props) {
			return h('div', {
				style: {
					display: 'flex', gap: 4, borderBottom: '1px solid var(--dsw-alias-border-l1, rgba(255,255,255,.09))',
					paddingBottom: 2,
				},
			}, props.items.map(function (it) {
				const on = props.active === it.key;
				return h('button', {
					key: it.key,
					onClick: function () { props.onChange(it.key); },
					style: {
						fontSize: 12, padding: '5px 14px', cursor: 'pointer',
						background: on ? 'var(--dsw-alias-bg-layer-2, rgba(255,255,255,.08))' : 'transparent',
						color: on ? 'var(--dsw-alias-label-primary)' : 'var(--dsw-alias-label-secondary)',
						border: 'none',
						borderBottom: on ? '2px solid var(--dsw-alias-brand-primary, #7eb8ff)' : '2px solid transparent',
						fontWeight: on ? 600 : 400,
					},
				}, it.label);
			}));
		}

		function Root() {
			const state = React.useState(null);
			const data = state[0];
			const setData = state[1];
			const tabState = React.useState('persona');
			const tab = tabState[0];
			const setTab = tabState[1];
			const openBarsState = React.useState(false);
			const openBars = openBarsState[0];
			const setOpenBars = openBarsState[1];
			const openQiState = React.useState('');
			const openQi = openQiState[0];
			const setOpenQi = openQiState[1];
			const tickState = React.useState(0);
			const setTick = tickState[1];
			const errState = React.useState('');
			const err = errState[0];
			const setErr = errState[1];
			// 看哪个库：空 = 当前工作区默认的那个
			const viewState = React.useState('');
			const viewDb = viewState[0];
			const setViewDb = viewState[1];

			React.useEffect(function () {
				let alive = true;
				function tick() {
					const url = '/sui/data' + (viewDb ? '?db=' + encodeURIComponent(viewDb) : '');
					fetch(url, { cache: 'no-store' })
						.then(function (r) { return r.json(); })
						.then(function (j) { if (alive) { setData(j); setErr(''); } })
						.catch(function (e) { if (alive) setErr(String((e && e.message) || e)); });
				}
				tick();
				const timer = setInterval(function () { if (!document.hidden) tick(); }, 10000);
				return function () { alive = false; clearInterval(timer); };
			}, [viewDb]);

			const d = data || {};
			const feels = d.feelings || [];
			const mems = d.recentMemories || [];
			const m = d.memories || {};
			const recent = d.recent || [];

			const head = h('div', { className: 'sui-head' },
				h('div', { className: 'sui-title' }, TITLE),
				h('div', { className: 'sui-sub' }, '三层记忆 · 记录 / 记忆 / 感觉'),
				(d.who || viewDb)
					? h('div', {
						style: {
							fontSize: 11, padding: '1px 8px', borderRadius: 999, marginLeft: 'auto',
							color: 'var(--dsw-alias-brand-primary, rgba(126,184,255,.95))',
							border: '1px solid var(--dsw-alias-brand-primary, rgba(126,184,255,.3))',
						},
					}, '看的是 ' + (d.who || (viewDb.split(/[\\/]/).slice(-3, -1)[0] || '这个库')))
					: null
			);

			if (err) {
				return h('div', { className: 'sui-root' },
					h('div', { className: 'sui-inner' },
						head,
						h('div', { className: 'sui-empty' }, '读不到数据：' + err))
				);
			}

			const cards = h('div', { className: 'sui-cards' },
				Card('记录', d.facts || 0, '发生过的事'),
				Card('记忆', m.total || 0, (m.confirmed || 0) + ' 对上 / ' + (m.split || 0) + ' 有分歧 / ' + (m.pending || 0) + ' 待旁听'),
				Card('感觉词', feels.length, '两边都对上的'),
				Card('小路', d.wishes || 0, '写给自己、不算数的')
			);

			const bars = feels.length
				? h('div', { className: 'sui-sec' }, feels.map(function (f) {
					return h(Bar, {
						key: f.keyword, keyword: f.keyword,
						share: f.share, weight: f.weight, hits: f.hits,
						spanDays: f.spanDays, contexts: f.contexts,
					});
				}))
				: h('div', { className: 'sui-empty' }, '还没有。两个提炼者都挑中的词才算。');

			// 七情：喜 怒 忧 思 悲 恐 惊，另加「平」。默认只给权重，点开才看底下挂了哪些说法。
			const roots = d.roots || [];
			const rootTotal = roots.reduce(function (s, x) { return s + (x.weight || 0); }, 0) || 1;
			const qiSec = h('div', { className: 'sui-sec' },
				h('div', { className: 'sui-sec-h' }, '七情'),
				h('div', { className: 'sui-sec', style: { gap: 1 } }, roots.map(function (r) {
					const share = Math.round(100 * (r.weight || 0) / rootTotal);
					const empty = !r.words || !r.words.length;
					const on = openQi === r.root;
					const tint = empty
						? 'var(--dsw-alias-label-secondary, rgba(200,200,210,.5))'
						: 'var(--dsw-alias-label-primary)';
					return h('div', { key: 'q' + r.root },
						h('div', {
							onClick: function () { if (!empty) setOpenQi(on ? '' : r.root); },
							style: {
								display: 'flex', alignItems: 'center', gap: 8, fontSize: 12,
								cursor: empty ? 'default' : 'pointer', padding: '2px 0',
							},
						},
							h('span', { style: { width: 18, flex: 'none', color: tint } }, r.root),
							h('div', {
								style: {
									flex: 1, height: 9, borderRadius: 4,
									background: 'var(--dsw-alias-bg-layer-2, rgba(255,255,255,.07))',
									overflow: 'hidden',
								},
							}, h('div', {
								style: {
									width: Math.max(share, r.weight ? 2 : 0) + '%', height: '100%',
									borderRadius: 4,
									background: empty ? 'transparent' : 'var(--dsw-alias-brand-primary, #7eb8ff)',
								},
							})),
							h('span', {
								style: {
									width: '3.4em', flex: 'none', textAlign: 'right',
									color: 'var(--dsw-alias-label-secondary)', fontVariantNumeric: 'tabular-nums',
								},
							}, share + '%'),
							h('span', {
								style: {
									width: '3.2em', flex: 'none', textAlign: 'right', fontSize: 11,
									color: 'var(--dsw-alias-label-secondary)', opacity: .5,
									fontVariantNumeric: 'tabular-nums',
								},
							}, (r.weight || 0).toFixed(1)),
							h('span', {
								style: {
									width: '1em', flex: 'none', opacity: empty ? 0 : .45,
									color: 'var(--dsw-alias-label-secondary)',
								},
							}, on ? '▾' : '▸')
						),
						on
							? h('div', {
								style: {
									paddingLeft: 26, paddingBottom: 4, fontSize: 11,
									color: 'var(--dsw-alias-label-secondary)',
								},
							}, r.words.map(function (w) { return w.keyword + ' ' + w.weight.toFixed(2); }).join('　'))
							: null
					);
				}))
			);

			// 六欲：生 死 耳 目 口 鼻。欲望指向哪儿，跟七情不是一层。
			const desires = d.desires || [];
			const desireSec = h('div', { className: 'sui-sec' },
				h('div', { className: 'sui-sec-h' }, '六欲 · 欲望指向哪儿'),
				h('div', { style: { display: 'flex', gap: 10, flexWrap: 'wrap' } }, desires.map(function (x, i) {
					const empty = !x.words || !x.words.length;
					return h('div', {
						key: 'd' + i,
						style: {
							fontSize: 12, padding: '3px 10px', borderRadius: 6,
							border: '1px solid ' + (empty
								? 'var(--dsw-alias-border-l1, rgba(255,255,255,.09))'
								: 'var(--dsw-alias-brand-primary, #7eb8ff)'),
							color: empty
								? 'var(--dsw-alias-label-secondary)'
								: 'var(--dsw-alias-label-primary)',
							opacity: empty ? .55 : 1,
						},
					},
						h('span', { style: { marginRight: 6 } }, x.desire),
						empty ? '—'
							: h('span', { style: { opacity: .75 } },
								x.words.map(function (w) { return w.keyword; }).join(' '))
					);
				})),
				h('div', { className: 'sui-foot' }, '七情是状态，六欲是方向。两样可以同时成立。')
			);

			// 具体说法：默认收起，点开才看。人看的是权重，不是一排名词。
			const personaSec = h('div', { className: 'sui-sec' },
				h('div', {
					className: 'sui-sec-h',
					onClick: function () { setOpenBars(!openBars); },
					style: { cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 6 },
				},
					h('span', null, '具体说法 · ' + feels.length + ' 个'),
					h('span', {
						style: { fontSize: 10, opacity: .45, color: 'var(--dsw-alias-label-secondary)' },
					}, openBars ? '▾' : '▸')
				),
				openBars ? bars : null,
				recent.length
					? h('div', { className: 'sui-foot' }, '最近还在撞的：' + recent.join('、'))
					: null
			);

			// 情绪：最近七天被撞出来的，会回落。跟人格不是一回事。
			const mood = d.mood || [];
			const moodSec = h('div', { className: 'sui-sec' },
				h('div', { className: 'sui-sec-h' }, '情绪 · 最近七天'),
				mood.length
					? h('div', { style: { display: 'flex', gap: 6, flexWrap: 'wrap' } }, mood.map(function (x, i) {
						return h('span', {
							key: 'mood' + i,
							style: {
								fontSize: 11, padding: '2px 8px', borderRadius: 10,
								color: 'var(--dsw-alias-label-primary)',
								background: 'var(--dsw-alias-bg-layer-2, rgba(255,255,255,.06))',
								border: '1px solid var(--dsw-alias-border-l1, rgba(255,255,255,.09))',
							},
						}, x.keyword + ' ' + x.hits);
					}))
					: h('div', { className: 'sui-foot' }, '这几天没有新的')
			);

			// 语气：此刻该怎么说
			const voice = d.voice || [];
			const voiceSec = h('div', { className: 'sui-sec' },
				h('div', { className: 'sui-sec-h' }, '语气 · 此刻该怎么说'),
				voice.length
					? h('div', { className: 'sui-sec', style: { gap: 3 } }, voice.map(function (v, i) {
						return h('div', {
							key: 'v' + i,
							style: { fontSize: 12, color: 'var(--dsw-alias-label-secondary)' },
						}, h('span', {
							style: { color: 'var(--dsw-alias-brand-primary, #7eb8ff)', marginRight: 8 },
						}, v.keyword), v.how);
					}))
					: h('div', { className: 'sui-foot' }, '还没有')
			);

			const memList = mems.length
				? h('div', { className: 'sui-sec' }, mems.map(function (x) {
					return h('div', { className: 'sui-mem', key: 'm' + x.id },
						h('div', { className: 'id' }, '#' + x.id),
						h('div', { className: 'tx' },
							x.text,
							x.words && x.words.length
								? h('span', {
									style: {
										fontFamily: 'ui-monospace, SFMono-Regular, Consolas, "Courier New", monospace',
										marginLeft: 8,
										color: 'var(--dsw-alias-brand-primary, rgba(126,184,255,.95))',
										letterSpacing: '.03em',
										whiteSpace: 'nowrap',
									},
								}, x.words.join(' '))
								: null,
							h('span', { className: 'sui-tag ' + (STATE_CLASS[x.state] || 'pend') },
								STATE_TEXT[x.state] || x.state),
							// 旁听从哪儿来的：空着或 same-context 就是账本上有窟窿
							x.by
								? h('span', {
									style: {
										fontSize: 10, marginLeft: 8,
										color: 'var(--dsw-alias-label-tertiary, rgba(255,255,255,.45))',
									},
								}, x.by)
								: null
						)
					);
				}))
				: h('div', { className: 'sui-empty' }, '还没有记忆。先用 sui_fact 记，再提炼。');

			const memSec = h('div', { className: 'sui-sec' },
				h('div', { className: 'sui-sec-h' }, '最近的记忆'),
				memList
			);

			const cardRow = cards;
			const perTab = {
				persona: [cardRow, qiSec, desireSec, personaSec, moodSec, voiceSec],
				memory: [memSec],
				archive: [h(Snapshot, { key: 'snap', data: d, viewDb: viewDb, onSaved: function () { setTick(function (x) { return x + 1; }); } })],
				params: [h(Settings, { key: 's', viewDb: viewDb })],
				libs: [h(People, {
					key: 'libs',
					viewDb: viewDb,
					onView: function (db) { setViewDb(db || ''); setTab('persona'); },
				})],
			};

			return h('div', { className: 'sui-root' },
				h('div', { className: 'sui-inner' },
					head,
					h(Tabs, {
						key: 'tabs',
						items: [
							{ key: 'persona', label: '人格' },
							{ key: 'memory', label: '记忆' },
							{ key: 'archive', label: '存档' },
							{ key: 'libs', label: '人' },
							{ key: 'params', label: '参数' },
						],
						active: tab,
						onChange: function (k) { setTab(k); },
					}),
					h('div', { key: 'body', className: 'sui-sec' }, perTab[tab] || null),
					(d.merges && d.merges.length)
						? h('div', { className: 'sui-sec' },
							h('div', { className: 'sui-sec-h' }, '归并过的词'),
							h('div', { className: 'sui-foot' },
								d.merges.map(function (g) {
									return g.name + ' ← ' + g.words.join('、');
								}).join('   ｜   ')))
						: null,
					h('div', { className: 'sui-foot' }, '更新于 ' + (d.now || '—') + '，每 10 秒刷新')
				)
			);
		}

		return {
			name: 'dsh-sui',
			inject: ['slots'],
			apply(ctx) {
				ctx.effect(function () {
					const style = document.createElement('style');
					style.id = 'sui-css';
					style.textContent = CSS;
					document.head.appendChild(style);
					return function () {
						try { style.remove(); } catch (e) { /* ignore */ }
					};
				});
				ctx.slots.inject('sidebar.panellist', function () {
					return ctx.slots.register({
						name: 'sidebar.panellist',
						id: PANEL_ID,
						order: 211,
						label: function () { return TITLE; },
					}, WheatIcon);
				});
				ctx.slots.inject('main', function () {
					return ctx.slots.register({
						name: 'main',
						key: PANEL_ID,
					}, function () { return h(Root); });
				});
			},
		};
	},
});















