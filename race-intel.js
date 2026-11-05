'use strict';
// KEIBA LAB 3.9: Race pace, pre-race forecast and market snapshot display.
// Odds/popularity are factual observations, never calculated from win probability.
function narDisplayMarket(record) {
  const latest = record.market;
  const snapshot = record.market_at_lock;
  const rows = new Map();
  for (const row of snapshot?.horses || []) {
    if (Number(row.odds) >= 1 && Number(row.odds) < 10000)
      rows.set(Number(row.no), {...row, observed_at: snapshot.updated_at});
  }
  let hasLatest = false;
  for (const row of latest?.horses || []) {
    if (Number(row.odds) >= 1 && Number(row.odds) < 10000) {
      rows.set(Number(row.no), row);
      hasLatest = true;
    }
  }
  return {horses: [...rows.values()], updated_at: hasLatest ? latest.updated_at : snapshot?.updated_at,
    snapshotOnly: !hasLatest && rows.size > 0};
}

function raceInsightHtml(record, source = 'NAR') {
  const esc = value => String(value ?? '').replace(/[&<>"']/g, ch => ({
    '&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#39;'
  }[ch]));
  const rawRunners = Array.isArray(record?.runners) ? record.runners :
    Array.isArray(record?.ranking) ? record.ranking :
    Array.isArray(record?.top3) ? record.top3 : [];
  // JRA saved runners use source/input order; sort by the frozen win estimate.
  // Older JRA ledgers only saved top3 numbers and names (no historical odds).
  const runners = rawRunners.map(x => typeof x === 'number' ?
    {no:x,name:record.horseNames?.[record.horseNos?.indexOf(x)] || '馬名未保存'} : x);
  if (!Array.isArray(record?.ranking)) {
    runners.sort((a,b) => Number(b.win_probability ?? -1) - Number(a.win_probability ?? -1));
  }
  if (!runners.length) return '';
  // Historic/preliminary NAR forecasts saved pre-lock odds separately.
  // Prefer the latest published quote, then a labelled saved pre-lock snapshot.
  const observedMarket = source === 'NAR' ? narDisplayMarket(record) :
    record?.market?.horses?.length ? record.market : record?.market_at_lock;
  const marketRows = observedMarket?.horses || (source === 'input' || source === 'JRA' ? runners : []);
  const market = new Map(marketRows.filter(x => Number.isInteger(Number(x.no)))
    .map(x => [Number(x.no), x]));
  const entries = runners.map((horse, i) => {
    const found = market.get(Number(horse.no)) || {};
    const rawOdd = found.odds;
    const odd = rawOdd === null || rawOdd === undefined || rawOdd === '' ? NaN : Number(rawOdd);
    const pop = Number(found.popularity);
    return {
      no: Number(horse.no), name: String(horse.name || ''), predictedRank: i + 1,
      p: Number(horse.win_probability), odd: Number.isFinite(odd) && odd >= 1 ? odd : null,
      retained: Boolean(found.observed_at),
      popularity: Number.isInteger(pop) && pop >= 1 && pop <= 50 ? pop : null,
      style: String(horse.runningStyle || horse.running_style || '').trim()
    };
  });
  const oddsSorted = entries.filter(x => x.odd !== null)
    .sort((a, b) => a.odd - b.odd || a.no - b.no);
  // Derive ties only when an official popularity number isn't supplied.
  if (oddsSorted.length === entries.length && !oddsSorted.some(x => x.retained)) oddsSorted.forEach(x => {
    if (x.popularity === null) x.popularity = oddsSorted.findIndex(y => y.odd === x.odd) + 1;
  });
  const styles = {'逃げ':[], '先行':[], '差し':[], '追込':[]};
  entries.forEach(x => {if (Object.prototype.hasOwnProperty.call(styles, x.style)) styles[x.style].push(x);});
  const covered = Object.values(styles).reduce((sum, rows) => sum + rows.length, 0);
  let pace = 'ペース判定不可';
  let paceText = '脚質データが不足しています。脚質を入力すると、逃げ・先行争いをもとに簡易展開を表示します。';
  if (covered >= Math.ceil(entries.length * 0.6)) {
    const escapees = styles['逃げ'].length;
    pace = escapees >= 3 ? '速い流れ寄り' : escapees === 2 ? 'やや速め' : escapees === 1 ? '平均ペース寄り' : 'スロー寄り';
    const nos = key => styles[key].slice(0, 4).map(x => x.no + '番').join('・') || '—';
    const late = [...styles['差し'], ...styles['追込']].slice(0, 4).map(x => x.no + '番').join('・') || '—';
    paceText = '逃げ候補 ' + nos('逃げ') + ' ／ 先行 ' + nos('先行') + ' ／ 差し・追込 ' + late;
  }
  const topGap = entries.length >= 2 && Number.isFinite(entries[0].p) && Number.isFinite(entries[1].p)
    ? ' ／ 予想1・2位の勝率推定差 ' + (100 * (entries[0].p - entries[1].p)).toFixed(1) + 'pt' : '';
  const formatItem = (x, i, kind) =>
    '<div class="intel-item"><span class="intel-rank">' + (i + 1) +
    '</span><span class="intel-horse"><b>' + esc(x.no) + '番</b> ' + esc(x.name) +
    '</span><span class="intel-odds">' + (x.odd === null ? '—' : esc(x.odd.toFixed(1)) + '倍' + (x.retained ? '（保存値）' : '')) +
    '<small>' + (kind === 'predict' ? (x.popularity === null ? '人気未取得' : esc(x.popularity) + '番人気') :
    '予想' + x.predictedRank + '位') + '</small></span></div>';
  const predicted = entries.slice(0, 5).map((x,i) => formatItem(x, i, 'predict')).join('');
  const popular = oddsSorted.length ? oddsSorted.slice(0, 5).map((x,i) => formatItem(x, i, 'pop')).join('') :
    '<p class="tiny muted">単勝オッズ未取得のため人気順を表示できません。</p>';
  const complete = oddsSorted.length ?
    '<details class="intel-all"><summary>全頭の人気順と予想順位を見る</summary>' +
    '<table class="intel-all-table"><thead><tr><th>人気</th><th>馬番・馬名</th><th>予想</th><th>単勝</th></tr></thead><tbody>' +
    oddsSorted.map(x => '<tr><td>' + (x.popularity === null ? '—' : esc(x.popularity) + '人気') + '</td><td>' + esc(x.no) +
      ' ' + esc(x.name) + '</td><td>' + x.predictedRank + '位</td><td>' +
      esc(x.odd.toFixed(1)) + '倍' + (x.retained ? '（保存値）' : '') + '</td></tr>').join('') + '</tbody></table></details>' : '';
  const savedAt = observedMarket?.updated_at ? new Date(observedMarket.updated_at).toLocaleString('ja-JP', {timeZone:'Asia/Tokyo'}) : '予想保存・入力時点';
  const label = source === 'NAR'
    ? ('地方競馬公式の単勝オッズ' + (observedMarket.snapshotOnly ? '（予想時点の保存値）' : '')) :
    source === 'JRA' ? '利用者が登録した単勝オッズ' : '入力した単勝オッズ';
  return '<div class="race-intel"><div class="race-intel-head"><span>🏁 展開予想・単勝オッズ・人気順</span><span class="pace-tag">' +
    esc(pace) + '</span></div><p class="pace-note">' + esc(paceText + topGap) +
    '<small>脚質からの簡易判断。騎手の作戦や実際のペースを予測できるとは限りません。</small></p>' +
    '<div class="intel-cols"><div class="intel-col"><h4>◎ 予想上位</h4>' + predicted +
    '</div><div class="intel-col"><h4>★ 人気順</h4>' + popular + '</div></div>' + complete +
    '<div class="intel-foot">' + esc(label + ' ／ ' + savedAt) +
    '。オッズは変動します。保存済みの予想や買い目には反映しません。</div></div>';
}