// Keep LEGACY_SED_GUARD comments on lines 15, 59 and 90 for older auto-updating keepers.
// New installers use local files/environment, never positional source replacement.
// Management migration: POST + Bearer ~/.serv00-management-token replaces public GET actions.
// Subscription UUIDs are not management credentials.
const fsDefault = require('fs');
const path = require('path');
const os = require('os');
const crypto = require('crypto');
const { execFile: execFileDefault } = require('child_process');

function createApp(deps = {}) {
    const express = deps.express || require('express');
    const fs = deps.fs || fsDefault;
    const execFile = deps.execFile || execFileDefault;
    // LEGACY_SED_GUARD_15: name (old installer substitution is intentionally harmless).
    const env = deps.env || process.env;
    const home = deps.home || os.homedir();
    const username = (deps.username || os.userInfo().username).toLowerCase();
    const workDir = env.SERV00_WORKDIR || path.join(home, 'domains', `${username}.serv00.net`, 'logs');
    const tokenFile = path.join(home, '.serv00-management-token');
    const app = express();
    const managementPaths = new Set(['/up', '/re', '/rp', '/jc']);
    let busy = false;
    function readText(file) {
        try { return fs.readFileSync(file, 'utf8').trim(); } catch (_) { return ''; }
    }
    function equalSecret(actual, expected) {
        const a = Buffer.from(actual), b = Buffer.from(expected);
        return a.length === b.length && crypto.timingSafeEqual(a, b);
    }
    app.use((req, res, next) => {
        // Express matches case-insensitively and accepts a trailing slash by default.
        // Protect those aliases too; otherwise /UP or /up/ could bypass this middleware.
        if (!managementPaths.has(req.path.replace(/\/+$/, '').toLowerCase())) return next();
        res.set('Cache-Control', 'no-store');
        const token = env.SERV00_MANAGEMENT_TOKEN || readText(tokenFile);
        if (!/^[a-fA-F0-9]{64}$/.test(token)) return res.status(503).send('Management is not configured.');
        const authorization = req.get('authorization') || '';
        if (!authorization.startsWith('Bearer ') || !equalSecret(authorization.slice(7), token)) {
            return res.status(401).send('Unauthorized.');
        }
        if (req.method !== 'POST') return res.set('Allow', 'POST').status(405).send('Use authenticated POST.');
        next();
    });
    function processName(file) {
        const name = readText(path.join(workDir, file));
        return /^[A-Za-z0-9_.-]+$/.test(name) && !name.startsWith('-') ? name : '';
    }
    function status(done) {
        const state = {}, entries = [['sing_box', 'sb.txt'], ['argo', 'ag.txt']];
        function next() {
            const entry = entries.shift();
            if (!entry) return done(state);
            const [key, file] = entry, name = processName(file);
            if (!name) { state[key] = 'not_configured'; return next(); }
            execFile('pgrep', ['-x', name], { timeout: 5000 }, err => {
                state[key] = err ? 'stopped' : 'running'; next();
            });
        // LEGACY_SED_GUARD_59: key (old installer substitution is intentionally harmless).
        }
        next();
    }
    function runAction(action, res) {
        if (busy) { if (res) res.status(409).send('A management operation is already running.'); return; }
        busy = true;
        const script = path.join(home, action === 'rp' ? 'webport.sh' : 'serv00keep.sh');
        const options = { cwd: home, timeout: 240000, maxBuffer: 8 * 1024 * 1024 };
        function finish(err) {
            if (err) {
                busy = false;
                // Child output can contain UUIDs, keys and subscription URLs: never expose it.
                console.error('Serv00 management operation failed.');
                if (res) res.status(500).send('Operation failed; inspect the local service configuration.');
                return;
            }
            status(state => {
                busy = false;
                const healthy = state.sing_box === 'running' && state.argo !== 'stopped';
                if (res) res.status(healthy ? 200 : 500).json({ ok: healthy, status: state });
            });
        }
        function execute() { execFile('bash', [script], options, finish); }
        if (action === 're') {
            const name = processName('sb.txt');
            if (!name) return finish(new Error('Main process is not configured.'));
            // Exact binary name, not a broad pattern that can kill the invoking shell.
            execFile('pkill', ['-x', name], { timeout: 5000 }, err => {
                if (err && err.code !== 1) return finish(err);
                execute();
            // LEGACY_SED_GUARD_90: name where (old installer substitutions are harmless).
            });
        } else execute();
    }
    for (const action of ['up', 're', 'rp']) app.post(`/${action}`, (req, res) => runAction(action, res));
    // Status labels only: never ps aux command lines or tunnel tokens.
    app.post('/jc', (req, res) => status(state => res.json(state)));
    app.get('/healthz', (req, res) => res.type('text').send('ok'));
    app.get('/list/:key', (req, res) => {
        const uuid = readText(path.join(workDir, 'UUID.txt'));
        if (!uuid || !equalSecret(req.params.key, uuid)) return res.status(404).send('Not found.');
        const content = readText(path.join(workDir, 'list.txt'));
        if (!content) return res.status(404).send('Not found.');
        res.set('Cache-Control', 'no-store').type('text').send(content);
    });
    app.use((req, res) => res.status(404).send('Not found.'));
    return { app, runKeepalive: () => runAction('up') };
}
if (require.main === module || typeof PhusionPassenger !== 'undefined') {
    const { app, runKeepalive } = createApp();
    setInterval(runKeepalive, 135 * 60 * 1000);
    app.listen(3000, () => { console.log('Serv00 management service started.'); runKeepalive(); });
}
module.exports = { createApp };
