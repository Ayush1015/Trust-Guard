'use strict';
const $ = id => document.getElementById(id);
const DEFAULT_API = 'http://localhost:5000/api/v1';
let apiBase = DEFAULT_API;
let activeTab = null;
function validApi(value) {
  const u = new URL(value);
  if (u.username || u.password || u.search || u.hash) throw new Error('Use an API URL without credentials, query or fragment.');
  if (u.protocol !== 'https:' && !(u.protocol === 'http:' && ['localhost','127.0.0.1'].includes(u.hostname))) throw new Error('Use HTTPS, or local HTTP on localhost/127.0.0.1.');
  return u.href.replace(/\/+$/, '');
}
function errorText(err) { return err.name === 'AbortError' ? 'The server took too long. No final assessment is available.' : err.message || 'Check failed.'; }
async function call(path, payload) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 180000);
  try {
    const res = await fetch(apiBase + path, {method:payload ? 'POST':'GET',headers:{'Content-Type':'application/json'},body:payload ? JSON.stringify(payload):undefined,signal:controller.signal});
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.error?.message || data.detail || `Server returned ${res.status}`);
    return data;
  } finally { clearTimeout(timeout); }
}
async function status() {
  try {
    const data = await call('/analyze/health');
    $('status').textContent = data.mlService?.status === 'UP' || data.mlService?.modelsReady ? 'Backend connected. ML service online.' : 'Gateway connected. Check ML service availability.';
  } catch (e) { $('status').textContent = 'Backend unavailable: ' + errorText(e); }
}
function showError(e) { $('result-box').hidden=false; $('result-title').textContent='No assessment'; $('result').textContent=errorText(e); $('result-box').scrollIntoView({block:'start'}); }
async function readPage(selectionOnly) {
  try {
    if (!activeTab?.id || !/^https?:/.test(activeTab.url || '')) throw new Error('Open a normal HTTP(S) web page first. Browser settings and store pages cannot be read.');
    const [out] = await chrome.scripting.executeScript({target:{tabId:activeTab.id},func:only => only ? window.getSelection().toString().slice(0,10000) : (document.querySelector('article') || document.querySelector('main') || document.body).innerText.slice(0,10000),args:[selectionOnly]});
    $('text').value = out.result || '';
    if (!$('text').value.trim()) throw new Error('No text found. Select a passage or paste text into the preview.');
    $('status').textContent='Text is in the preview only. Choose a check to send it.';
  } catch(e) { showError(e); }
}
function render(data, type) {
  $('result-box').hidden=false;
  $('result-title').textContent = type === 'review' ? 'Writing-origin estimate' : type === 'phishing' ? 'URL risk estimate' : 'News assessment';
  const label = data.poll?.abstain ? 'Uncertain - insufficient model agreement' : (data.labelDisplay || data.label || 'Not verified');
  const lines = [label];
  if (data.confidence != null) lines.push(`Model score: ${data.confidence}% (not calibrated probability of truth or safety)`);
  if (data.explanation) lines.push(typeof data.explanation === 'string' ? data.explanation : JSON.stringify(data.explanation));
  if (type === 'review') lines.push('AI-like or human-like wording does not prove deception or authenticity.');
  if (type === 'news') lines.push('Source agreement is estimated. A source can repeat a false claim.');
  $('result').textContent=lines.join('\n\n');
  // Keep source evidence as plain text; never execute page or server markup.
  const verification = data.claimVerification || data.claim_verification;
  $('result-box').scrollIntoView({block:'start'});
  const articles = verification?.sources || verification?.articles || verification?.results || [];
  for (const item of articles.slice(0,5)) {
    const block = document.createElement('blockquote');
    block.textContent = `${item.verdict || item.stance || 'inconclusive'}: ${item.matchedPassage || item.matched_passage || 'No matched passage'}`;
    $('result').append(block);
    try { const u=new URL(item.url); if(u.protocol==='https:' || u.protocol==='http:') {const a=document.createElement('a');a.textContent=u.hostname;a.href=u.href;a.target='_blank';a.rel='noopener noreferrer';$('result').append(a);} } catch {}
  }
}
async function check(type) {
  const buttons=[...document.querySelectorAll('button')];
  try {
    let payload;
    if(type==='phishing') {
      if(!activeTab?.url || !/^https?:/.test(activeTab.url)) throw new Error('Open a normal web page first.');
      payload={url:activeTab.url};
    } else {
      const text=$('text').value.trim();
      if(text.length<10) throw new Error('Add at least 10 characters of claim or review text first.');
      payload={text};
    }
    buttons.forEach(b=>b.disabled=true); $('result-box').hidden=false; $('result-title').textContent='Checking...'; $('result').textContent='Waiting for the TrustGuard server. Keep this popup open.';
    render(await call('/analyze/'+type,payload),type);
  } catch(e) {showError(e);} finally {buttons.forEach(b=>b.disabled=false);}
}
$('save').addEventListener('click',async()=>{
  try {const next=validApi($('api').value.trim());const u=new URL(next);if(u.protocol==='https:') {const granted=await chrome.permissions.request({origins:[u.origin+'/*']});if(!granted)throw new Error('Backend access was not allowed.');}apiBase=next;await chrome.storage.local.set({apiBaseUrl:apiBase});await status();}catch(e){showError(e);}
});
$('read-selection').addEventListener('click',()=>readPage(true));
$('read-page').addEventListener('click',()=>readPage(false));
$('news-check').addEventListener('click',()=>check('news'));
$('review-check').addEventListener('click',()=>check('review'));
$('url-check').addEventListener('click',()=>check('phishing'));
(async()=>{const saved=await chrome.storage.local.get('apiBaseUrl');try{apiBase=validApi(saved.apiBaseUrl || DEFAULT_API);}catch{}$('api').value=apiBase;[activeTab]=await chrome.tabs.query({active:true,currentWindow:true});$('page-url').textContent=activeTab?.url || 'No page selected';await status();})();
