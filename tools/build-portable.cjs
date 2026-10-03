/* Build one self-contained folder: the program plus a worker executable per game.
 *
 * Everything the app needs at runtime is placed here, so the folder can be copied
 * to another machine and run with no install step. Workers are rebuilt from the
 * current executable rather than copied, so they can never be stale.
 */
const fs = require('node:fs');
const path = require('node:path');

const root = path.resolve(__dirname, '..');
const target = path.join(root, 'dist', 'worthlesstask');

// A staged build in outputs/ wins; otherwise rebuild from the folder already
// shipped. Never seed from dist/ unless nothing else exists — that would rebuild
// the folder from itself and silently keep serving an old executable.
const candidates = [path.join(root, 'outputs', 'worthlesstask.exe'), path.join(root, 'build', 'worthlesstask.exe')];
const source = candidates.find(candidate => fs.existsSync(candidate));
if (!source) {
  console.error(`missing ${candidates[0]}. Build the executable first.`);
  process.exit(1);
}

// The installable name is canonical: install() and the shortcuts expect worthlesstask.exe.
// The library is read from the source tree first; a copy left in outputs/ is a fallback.
const libraryPath = [path.join(root, 'library.json'), path.join(root, 'build', 'library.json'),
                     path.join(target, 'library.json')].find(candidate => fs.existsSync(candidate));
const library = JSON.parse(fs.readFileSync(libraryPath, 'utf8'));
const games = Array.isArray(library.games) ? library.games : [];

// Nothing here is deleted: the host environment refuses to trash executables, and
// overwriting is both safer and enough. Every file the folder needs is rewritten
// below, so a stale worker for a removed game is the only thing that can linger.
fs.mkdirSync(target, { recursive: true });
fs.mkdirSync(path.join(target, 'icons'), { recursive: true });

const sha256 = buf => require('crypto').createHash('sha256').update(buf).digest('hex');
const problems = [];

// Write bytes through a file descriptor, then verify what actually landed.
//
// fs.writeFileSync and fs.copyFileSync both under-write large files in this
// environment: asked for N bytes they quietly write fewer and report success. That
// ships an executable which looks correct and serves stale code. Opening, writing
// through the descriptor, fsync, then hashing the result catches it.
const writeExact = (dest, payload) => {
  const fd = fs.openSync(dest, 'w');
  try {
    const written = fs.writeSync(fd, payload, 0, payload.length, 0);
    fs.fsyncSync(fd);
    if (written !== payload.length) {
      problems.push(`${path.basename(dest)}: wrote ${written}/${payload.length} bytes`);
    }
  } finally {
    fs.closeSync(fd);
  }
  const onDisk = fs.readFileSync(dest);
  if (onDisk.length !== payload.length || sha256(onDisk) !== sha256(payload)) {
    problems.push(`${path.basename(dest)}: on disk ${onDisk.length}/${payload.length} bytes, sha mismatch`);
  }
};

const exe = fs.readFileSync(source);
const expectedSha = sha256(exe);
const copyExe = relName => {
  const dest = path.join(target, ...relName.split(/[\\/]+/));
  fs.mkdirSync(path.dirname(dest), { recursive: true });
  writeExact(dest, exe);
};

copyExe('worthlesstask.exe');
for (const game of games) {
  if (game.executable && /\.exe$/i.test(game.executable)) {
    copyExe(game.executable);
  }
  if (game.executable_rel && /\.exe$/i.test(game.executable_rel) && game.executable_rel !== game.executable) {
    copyExe(game.executable_rel);
  }
}

// The library travels with the folder: copying it to another machine keeps the games.
writeExact(path.join(target, 'library.json'), fs.readFileSync(libraryPath));
writeExact(path.join(target, 'config.example.json'), fs.readFileSync(path.join(root, 'config.example.json')));
writeExact(path.join(target, 'worthlesstask.ico'), fs.readFileSync(path.join(root, 'assets', 'worthlesstask.ico')));
writeExact(path.join(target, 'RUN.cmd'), Buffer.from([
  '@echo off',
  'REM Portable worthlesstask: start the local dashboard and open it in the browser.',
  'REM First run downloads the Discord catalogue and builds one exe per game.',
  'cd /d "%~dp0"',
  'start "" "%~dp0worthlesstask.exe"',
  ''
].join('\r\n'), 'utf8'));

// Drop anything the folder should not carry: a worker for a game that has since
// been removed, and runtime state created by running the app from this folder.
const wanted = new Set([
  'worthlesstask.exe',
  'worthlesstask.ico',
  ...games.map(game => game.executable).filter(Boolean),
  ...games.map(game => game.executable_rel ? game.executable_rel.split(/[\\/]+/)[0] : null).filter(Boolean),
]);
for (const entry of fs.readdirSync(target)) {
  if (entry === 'icons' || wanted.has(entry)) continue;
  // Stray icons and workers from a previous library, plus runtime state created by
  // running the app from this folder.
  if (/\.(exe|ico)$/i.test(entry) || entry === '.cache') {
    fs.rmSync(path.join(target, entry), { recursive: true, force: true });
  }
}

if (problems.length) {
  console.error('copy verification FAILED:');
  for (const problem of problems) console.error('  ' + problem);
  process.exit(2);
}

console.log(`built ${target} (${games.length} worker${games.length === 1 ? '' : 's'}, sha ${expectedSha.slice(0, 12)})`);
for (const file of fs.readdirSync(target).sort()) {
  const stat = fs.statSync(path.join(target, file));
  console.log(`  ${file}${stat.isDirectory() ? '/' : ` (${stat.size} bytes)`}`);
}
