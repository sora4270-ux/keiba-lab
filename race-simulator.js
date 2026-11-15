(function (root) {
  'use strict';

  const TRIALS = 5000;
  const WEIGHT_FIELDS = ['win_probability', 'place_weight', 'show_weight'];

  function raceInputs(rows) {
    if (!Array.isArray(rows) || rows.length < 3 || rows.length > 24) return null;
    const numbers = new Set();
    const runners = [];
    for (const row of rows) {
      const no = Number(row?.no);
      const name = typeof row?.name === 'string' && row.name.trim();
      const weights = WEIGHT_FIELDS.map(key => row?.[key] ?? row?.win_probability);
      if (!Number.isInteger(no) || no < 1 || no > 24 || numbers.has(no) || !name ||
          weights.some(value => !Number.isFinite(value) || value < 0)) return null;
      numbers.add(no);
      runners.push({ no, name, weights });
    }
    if (WEIGHT_FIELDS.some((_, stage) => !runners.some(runner => runner.weights[stage] > 0))) return null;
    return runners.sort((a, b) => a.no - b.no);
  }

  function sampleOrder(runners, random = Math.random) {
    const field = runners.slice();
    const finish = [];
    while (field.length) {
      const stage = Math.min(finish.length, 2);
      const weight = runner => Math.max(runner.weights[stage], 1e-12);
      let draw = random() * field.reduce((sum, runner) => sum + weight(runner), 0);
      const selected = field.findIndex(runner => (draw -= weight(runner)) < 0);
      finish.push(field.splice(selected < 0 ? field.length - 1 : selected, 1)[0]);
    }
    return finish;
  }

  function estimate(runners, trials = TRIALS) {
    // A fixed seed keeps the probability table stable when replaying the animation.
    let state = 314159265;
    const random = () => {
      state = (Math.imul(state, 1664525) + 1013904223) >>> 0;
      return state / 4294967296;
    };
    const counts = new Map(runners.map(runner => [runner.no, {runner, win:0, place:0, show:0, rank:0}]));
    for (let i = 0; i < trials; i++) {
      sampleOrder(runners, random).forEach((runner, rank) => {
        const item = counts.get(runner.no);
        if (rank === 0) item.win++;
        if (rank === 1) item.place++;
        if (rank === 2) item.show++;
        item.rank += rank + 1;
      });
    }
    return [...counts.values()].sort((a, b) => b.win - a.win || a.rank - b.rank || a.runner.no - b.runner.no);
  }

  function bind(dialog) {
    const get = name => dialog.querySelector('[data-sim-' + name + ']');
    const choice = get('choice');
    const start = get('start');
    const track = get('track');
    const finish = get('finish');
    const status = get('status');
    const percent = n => (100 * n / TRIALS).toFixed(1) + '%';
    let race = [];
    let lanes = new Map();
    let frame = 0;
    let opener;

    function element(tag, value, className) {
      const node = document.createElement(tag);
      if (className) node.className = className;
      if (value != null) node.textContent = value;
      return node;
    }

    function open(button, payload) {
      const field = raceInputs(payload.rows);
      if (!field) return;
      race = field;
      opener = button;
      get('title').textContent = payload.title;
      get('source').textContent = payload.source;
      status.textContent = '';
      finish.replaceChildren();
      start.textContent = 'レース開始';
      start.disabled = false;
      choice.disabled = false;
      choice.replaceChildren(new Option('応援する馬を選ぶ（任意）', ''));
      lanes = new Map(race.map(runner => {
        choice.add(new Option(runner.no + '番 ' + runner.name, runner.no));
        const lane = element('div', null, 'sim-lane');
        const label = element('span', runner.no + ' ' + runner.name, 'sim-horse-name');
        label.title = runner.name;
        const course = element('span', null, 'sim-course');
        const marker = element('span', '🐎', 'sim-marker');
        course.append(marker);
        lane.append(label, course);
        return [runner.no, {lane, marker}];
      }));
      track.replaceChildren(...[...lanes.values()].map(item => item.lane));
      const results = estimate(race);
      get('stats').replaceChildren(...results.map(({runner, win, place, show, rank}) => {
        const row = element('tr');
        const name = element('th', runner.no + ' ' + runner.name);
        name.scope = 'row';
        const wins = element('td', percent(win));
        const second = element('td', percent(place));
        const third = element('td', percent(show));
        const podium = element('td', percent(win + place + show));
        const average = element('td', (rank / TRIALS).toFixed(1));
        row.append(name, wins, second, third, podium, average);
        return row;
      }));
      dialog.showModal();
    }

    document.addEventListener('click', event => {
      const button = event.target.closest('[data-race-simulation]');
      if (button) open(button, JSON.parse(button.dataset.raceSimulation));
    });

    start.addEventListener('click', () => {
      const order = sampleOrder(race);
      const selected = Number(choice.value);
      for (const {lane, marker} of lanes.values()) {
        lane.classList.remove('sim-winner');
        marker.style.left = '0px';
      }
      finish.replaceChildren();
      start.disabled = true;
      choice.disabled = true;
      status.textContent = '出走中…';
      const started = performance.now();

      function complete() {
        lanes.get(order[0].no).lane.classList.add('sim-winner');
        finish.replaceChildren(...order.map(runner => element('li', runner.no + '番 ' + runner.name)));
        const rank = order.findIndex(runner => runner.no === selected) + 1;
        status.textContent = '1着 ' + order[0].no + '番 ' + order[0].name +
          (rank ? ' ／ 応援馬 ' + rank + '着' : '');
        start.disabled = false;
        choice.disabled = false;
        start.textContent = 'もう一度走らせる';
        frame = 0;
      }

      const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
      const routes = order.map((runner, rank) => ({
        marker: lanes.get(runner.no).marker,
        duration: 2200 + rank * 1400 / Math.max(1, order.length - 1),
        surge: (Math.random() - .5) * .38
      }));
      function draw(now) {
        const elapsed = reduced ? 3600 : now - started;
        for (const {marker, duration, surge} of routes) {
          const t = Math.min(1, elapsed / duration);
          const progress = t + surge * Math.sin(Math.PI * t);
          marker.style.left = 'calc(' + (progress * 100) + '% - ' + (progress * 28) + 'px)';
        }
        if (elapsed >= 3600) complete();
        else frame = requestAnimationFrame(draw);
      }
      frame = requestAnimationFrame(draw);
    });
    dialog.addEventListener('close', () => {
      cancelAnimationFrame(frame);
      frame = 0;
      if (opener?.isConnected) opener.focus();
    });
  }

  const api = {raceInputs, sampleOrder, estimate, bind};
  if (typeof module === 'object' && module.exports) module.exports = api;
  else root.KeibaSimulation = api;
})(globalThis);
