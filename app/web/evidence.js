/* Local document search. Files stay in the browser. */
'use strict';

function evidenceTokens(text) {
 const tokens = new Set();
 for (const word of text.normalize('NFKC').toLowerCase().match(/\p{Script=Han}+|(?:(?!\p{Script=Han})[\p{L}\p{N}_-])+/gu) || []) {
  if (!/^\p{Script=Han}+$/u.test(word) || word.length === 1) {
   tokens.add(word);
   continue;
  }
  const chars = Array.from(word);
  for (let i = 0; i + 1 < chars.length; i++) tokens.add(chars[i] + chars[i + 1]);
 }
 return tokens;
}

function findEvidence(query, documents) {
 const wanted = evidenceTokens(query);
 const hits = [];
 for (const {name, text} of documents) {
  text.split(/\r\n|\r|\n/).forEach((line, index) => {
   const tokens = evidenceTokens(line);
   const score = [...wanted].filter(token => tokens.has(token)).length;
   if (score) hits.push({name, line: index + 1, text: line, score});
  });
 }
 return hits.sort((a,b) => b.score - a.score || a.name.localeCompare(b.name) || a.line - b.line).slice(0,5);
}

function openEvidence() {
 modal(`<h2>本地论文与技术文档证据助手</h2>
 <p>选择 UTF-8 的 TXT 或 Markdown 文件，输入要找的词。结果按匹配程度排序，并附文件名和行号，可回到原文核对。</p>
 <form id="evidence-form">
 <label for="evidence-files">本地文件，最多 10 份，每份 1 MiB</label>
 <input id="evidence-files" type="file" multiple accept=".md,.txt,text/plain,text/markdown" required>
 <label for="evidence-query">要查找什么</label>
 <input id="evidence-query" maxlength="200" required placeholder="例如 随机种子 或 batch size">
 <div class="row-actions"><button class="primary" type="submit">查找原文</button></div>
 </form><div id="evidence-results" aria-live="polite"></div>`);
 $('#evidence-form').addEventListener('submit', async event => {
  event.preventDefault();
  const results = $('#evidence-results');
  const files = Array.from($('#evidence-files').files);
  const query = $('#evidence-query').value.trim();
  if (files.length > 10 || files.some(file => file.size > 1024 ** 2 || !/\.(txt|md)$/i.test(file.name))) {
   results.textContent = '请选择最多 10 份 TXT 或 Markdown 文件，每份不超过 1 MiB。';
   return;
  }
  if (!evidenceTokens(query).size) {
   results.textContent = '请输入至少一个关键词。';
   return;
  }
  try {
   const decoder = new TextDecoder('utf-8', {fatal:true});
   const documents = await Promise.all(files.map(async file => ({
    name:file.name,
    text:decoder.decode(await file.arrayBuffer())
   })));
   const hits = findEvidence(query,documents);
   results.innerHTML = hits.length ? '<h3>候选原文</h3>' + hits.map(hit =>
    `<section class="question"><small>${esc(hit.name)} · 第 ${hit.line} 行</small><pre>${esc(hit.text.slice(0,600))}${hit.text.length>600?'\n（此行较长，请回原文查看）':''}</pre></section>`
   ).join('') : '<p>没有找到匹配的原文，待复核。可以换一个关键词，或补充资料。</p>';
  } catch {
   results.textContent = '文件读取失败。请确认文件可读，并使用 UTF-8 编码保存。';
  }
 });
}
