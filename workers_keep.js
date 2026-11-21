// Set Worker secret SERV00_TARGETS to JSON, for example:
// [{"url":"https://s1.user.serv00.net/up","token":"<64-character management token>"}]
// Old public GET keepalive links are deliberately no longer supported.
addEventListener('scheduled', event => event.waitUntil(handleScheduled()));
const TIMEOUT = 250000;
async function fetchWithTimeout(target) {
  const url = new URL(target.url);
  if (url.protocol !== 'https:' || url.username || url.password ||
      !['/up', '/re'].includes(url.pathname) || !/^[a-fA-F0-9]{64}$/.test(target.token || '')) {
    throw new Error('Use an HTTPS /up or /re URL and a separate management token.');
  }
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), TIMEOUT);
  try {
    const response = await fetch(url.toString(), {
      method: 'POST', headers: { Authorization: `Bearer ${target.token}` },
      redirect: 'error', signal: controller.signal
    });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const result = await response.json();
    if (result.ok !== true) throw new Error('Service did not confirm a healthy operation.');
    console.log('✅ 保活操作完成');
    return true;
  } catch (error) {
    // Never log URLs, headers or response bodies containing credentials.
    console.warn(`❌ 保活失败: ${error.name === 'AbortError' ? 'timeout' : 'request rejected'}`);
    return false;
  } finally { clearTimeout(timeout); }
}
async function handleScheduled() {
  const targets = JSON.parse(typeof SERV00_TARGETS === 'string' ? SERV00_TARGETS : '[]');
  if (!Array.isArray(targets) || targets.length === 0) throw new Error('Configure the SERV00_TARGETS JSON secret.');
  let failed = false;
  for (let i = 0; i < targets.length; i += 4) {
    const results = await Promise.all(targets.slice(i, i + 4).map(fetchWithTimeout));
    if (results.some(ok => !ok)) failed = true;
  }
  if (failed) throw new Error('One or more keepalive operations failed.');
}
