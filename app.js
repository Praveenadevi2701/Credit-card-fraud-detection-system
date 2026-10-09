const $ = id => document.getElementById(id);
const esc = s => String(s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const inr = n => '₹' + Number(n).toLocaleString('en-IN');
const api = async (url, opts) => {
  const r = await fetch(url, opts && {headers:{'Content-Type':'application/json'}, ...opts});
  const d = await r.json();
  if (!r.ok) throw new Error(d.error || 'Something went wrong');
  return d;
};
const post = (url, body) => api(url, {method:'POST', body: JSON.stringify(body || {})});

async function loadStats(){
  const s = await api('/api/stats');
  $('stats').innerHTML = [
    ['', s.total, 'Checked'], ['ok', s.approved, 'Approved'], ['warn', s.review, 'Held for review'],
    ['bad', s.blocked, 'Blocked'], ['bad', s.breaches, 'Limit breaches'], ['', inr(s.amount_blocked), 'Amount blocked']
  ].map(([c,v,l]) => `<div class="stat ${c}"><b>${esc(v)}</b><span>${l}</span></div>`).join('');
}

async function loadCards(){
  const cs = await api('/api/cards');
  const sel = $('card'), keep = sel.value;
  sel.innerHTML = cs.map(c => `<option value="${esc(c.id)}">${esc(c.holder)} •••• ${esc(c.last4)}</option>`).join('');
  if (keep) sel.value = keep;
  $('cards').innerHTML = cs.map(c => {
    const pct = Math.min(100, c.spent_today / c.daily_limit * 100);
    const cls = pct >= 100 ? 'over' : pct >= 80 ? 'hot' : '';
    return `<div class="card ${c.frozen ? 'frozen' : ''}">
      <header><span>${esc(c.holder)}</span><span>•••• ${esc(c.last4)}</span></header>
      <div class="bar"><i class="${cls}" style="width:${pct}%"></i></div>
      <small>${inr(c.spent_today)} of ${inr(c.daily_limit)} today · max ${inr(c.txn_limit)} per payment</small>
      <button class="ghost" data-id="${esc(c.id)}">${c.frozen ? 'Unfreeze card' : 'Freeze card'}</button></div>`;
  }).join('');
  document.querySelectorAll('.card button').forEach(b => b.onclick = async () => { await post(`/api/cards/${b.dataset.id}/toggle`); refresh(); });
}

async function loadRows(){
  const tx = await api('/api/transactions?status=' + $('filter').value);
  $('rows').innerHTML = tx.length ? tx.map(x => `<tr>
    <td>${esc(x.time.replace('T',' '))}</td><td>${esc(x.card)}</td><td>${esc(x.merchant)}<br><small>${esc(x.category)} · ${esc(x.country)}</small></td>
    <td>${inr(x.amount)}</td><td>${x.risk}</td><td><span class="tag ${x.status}">${x.status}</span></td>
    <td>${x.reasons.map(esc).join('<br>') || 'Looks normal'}</td></tr>`).join('')
    : '<tr><td colspan="7" class="empty">No transactions yet. Run a check above.</td></tr>';
}

function showResult(r){
  const colour = r.status === 'APPROVED' ? 'var(--ok)' : r.status === 'REVIEW' ? 'var(--warn)' : 'var(--bad)';
  const text = {APPROVED:'Approved', REVIEW:'Held for review', BLOCKED:'Blocked'}[r.status];
  $('result').hidden = false;
  $('result').innerHTML = `<div class="gauge" style="--p:${r.risk};--c:${colour}"><div><span><b>${r.risk}</b><br><small>risk score</small></span></div></div>
    <div><div class="verdict" style="color:${colour}">${text}</div>
    ${r.limit_breach ? '<div class="alert">Limit breached on this card</div>' : ''}
    <ul>${r.reasons.length ? r.reasons.map(x => `<li>${esc(x)}</li>`).join('') : '<li>No risk signals found</li>'}</ul></div>`;
}

const refresh = () => Promise.all([loadStats(), loadCards(), loadRows()]);

$('run').onclick = async () => {
  try {
    const r = await post('/api/check', {card_id:$('card').value, amount:$('amount').value,
      merchant:$('merchant').value, category:$('category').value, country:$('country').value});
    showResult(r); refresh();
  } catch (e) { alert(e.message); }
};
$('toggleAdd').onclick = () => $('addCard').hidden = !$('addCard').hidden;
$('saveCard').onclick = async () => {
  try {
    await post('/api/cards', {holder:$('n_holder').value, last4:$('n_last4').value, home_country:$('n_country').value,
      txn_limit:$('n_txn').value, daily_limit:$('n_daily').value});
    $('addCard').hidden = true; refresh();
  } catch (e) { alert(e.message); }
};
$('filter').onchange = loadRows;
$('reset').onclick = async () => { if (confirm('Clear all transactions and cards?')) { await post('/api/reset'); $('result').hidden = true; refresh(); } };
refresh();
