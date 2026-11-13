#!/usr/bin/env node
// VeriCode post-generation API audit (TypeScript compiler API, nothing is executed).
// stdin:  {"projectRoot": "<sandbox copy>", "depsRoot": "<original project, optional>",
//          "files": [{"path": "src/a.ts", "lines": [3,4] | null}]}
// stdout: {"findings": [{file, line, kind: "deprecated"|"error", code, message, api, package, version, deprecated}]}
// Only third-party symbols (declared under node_modules) on the listed lines are reported.
'use strict'
const path = require('path')
const fs = require('fs')
const ts = require('typescript')

function readStdin() {
  return new Promise((res) => { let d = ''; process.stdin.on('data', (c) => (d += c)); process.stdin.on('end', () => res(d)) })
}

const norm = (p) => p.replace(/\\/g, '/')
const NM = '/node_modules/'  // TypeScript file names always use '/', also on Windows

function pkgOf(file) {
  file = norm(file)
  const i = file.lastIndexOf(NM)
  if (i < 0) return null
  const rest = file.slice(i + NM.length).split('/')
  const name = rest[0].startsWith('@') ? `${rest[0]}/${rest[1]}` : rest[0]
  const root = file.slice(0, i + NM.length) + name
  let version = null
  try { version = JSON.parse(fs.readFileSync(path.join(root, 'package.json'), 'utf8')).version } catch { /* ignore */ }
  // @types/foo describes foo
  return { name: name.startsWith('@types/') ? name.slice(7).replace('__', '/') : name, version }
}

function deprecatedTag(decl) {
  if (!decl) return null
  for (const tag of ts.getJSDocTags(decl)) {
    if (tag.tagName.text === 'deprecated') return (ts.getTextOfJSDocComment(tag.comment) || 'marked @deprecated').trim()
  }
  return null
}

function thirdPartyDecl(decls) {
  return (decls || []).find((d) => d.getSourceFile().fileName.includes(NM)) || null
}

function qualName(checker, sym) {
  const fq = checker.getFullyQualifiedName(sym)
  return fq.replace(/^"[^"]*"\./, '')
}

function loadOptions(root) {
  const cfg = ts.findConfigFile(root, ts.sys.fileExists, 'tsconfig.json')
  const base = { strict: true, target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ESNext, moduleResolution: ts.ModuleResolutionKind.Bundler,
    esModuleInterop: true, skipLibCheck: true, allowJs: true, checkJs: false, noEmit: true, types: [] }
  if (!cfg || !norm(cfg).startsWith(norm(root))) return base  // findConfigFile returns '/' paths, root may use '\\'
  const parsed = ts.parseJsonConfigFileContent(ts.readConfigFile(cfg, ts.sys.readFile).config || {}, ts.sys, path.dirname(cfg))
  return { ...parsed.options, noEmit: true, skipLibCheck: true, allowJs: true }  // generated .js files are audited too
}

async function main() {
  const req = JSON.parse(await readStdin())
  const root = path.resolve(req.projectRoot)
  const depsRoot = req.depsRoot ? path.resolve(req.depsRoot) : root
  const redirect = (p) => {
    const local = norm(path.join(root, 'node_modules'))
    const np = norm(p)
    if (depsRoot !== root && np.startsWith(local) && !fs.existsSync(local)) return norm(path.join(depsRoot, 'node_modules')) + np.slice(local.length)
    return p
  }
  const options = loadOptions(root)
  const host = ts.createCompilerHost(options, true)
  const orig = { fileExists: host.fileExists, readFile: host.readFile, getSourceFile: host.getSourceFile, directoryExists: host.directoryExists }
  host.fileExists = (p) => orig.fileExists.call(host, redirect(p))
  host.readFile = (p) => orig.readFile.call(host, redirect(p))
  host.directoryExists = (p) => (orig.directoryExists ? orig.directoryExists.call(host, redirect(p)) : true)
  host.getSourceFile = (p, lang, onErr, create) => orig.getSourceFile.call(host, redirect(p), lang, onErr, create)
  host.realpath = (p) => redirect(p)

  const files = req.files.map((f) => ({ abs: path.join(root, f.path), rel: f.path, lines: f.lines ? new Set(f.lines) : null }))
  const program = ts.createProgram(files.map((f) => f.abs), options, host)
  const checker = program.getTypeChecker()
  const findings = []
  const unreadable = []
  const seen = new Set()
  const push = (f) => { const k = `${f.file}:${f.line}:${f.kind}:${f.api}:${f.kind === 'deprecated' ? '' : f.code}`; if (!seen.has(k)) { seen.add(k); findings.push(f) } }

  for (const f of files) {
    const sf = program.getSourceFile(f.abs)
    if (!sf) { unreadable.push(f.rel); continue }  // reported: a file we could not load was NOT checked
    const lineOf = (pos) => sf.getLineAndCharacterOfPosition(pos).line + 1
    const onLine = (node) => !f.lines || f.lines.has(lineOf(node.getStart(sf)))

    // 1) deprecated third-party symbols / overloads used on added lines
    const visit = (node) => {
      if ((ts.isIdentifier(node) || ts.isPrivateIdentifier(node)) && onLine(node)) {
        let sym = checker.getSymbolAtLocation(node)
        if (sym && sym.flags & ts.SymbolFlags.Alias) { try { sym = checker.getAliasedSymbol(sym) } catch { /* ignore */ } }
        const decl = sym && thirdPartyDecl(sym.declarations)
        const dep = decl && (sym.declarations || []).every((d) => deprecatedTag(d)) ? deprecatedTag(decl) : null
        if (decl && dep) {
          const pkg = pkgOf(decl.getSourceFile().fileName) || {}
          push({ file: f.rel, line: lineOf(node.getStart(sf)), kind: 'deprecated', code: 6385, api: qualName(checker, sym),
            message: `'${node.text}' is deprecated in ${pkg.name}@${pkg.version}: ${dep}`, package: pkg.name, version: pkg.version, deprecated: dep })
        }
      }
      const calleeName = (ts.isCallExpression(node) || ts.isNewExpression(node))
        ? (ts.isPropertyAccessExpression(node.expression) ? node.expression.name : node.expression) : null
      if (calleeName && onLine(calleeName)) {  // line of the called name: a multiline chain is one use, not two
        const sig = checker.getResolvedSignature(node)
        const decl = sig && sig.declaration
        if (decl && decl.getSourceFile && decl.getSourceFile().fileName.includes(NM)) {
          const dep = deprecatedTag(decl)
          if (dep) {
            const callee = ts.isCallExpression(node) ? node.expression : node.expression
            const sym = checker.getSymbolAtLocation(ts.isPropertyAccessExpression(callee) ? callee.name : callee)
            const pkg = pkgOf(decl.getSourceFile().fileName) || {}
            push({ file: f.rel, line: lineOf(calleeName.getStart(sf)), kind: 'deprecated', code: 6387, api: sym ? qualName(checker, sym) : callee.getText(sf),
              message: `this overload of '${callee.getText(sf)}' is deprecated in ${pkg.name}@${pkg.version}: ${dep}`, package: pkg.name, version: pkg.version, deprecated: dep })
          }
        }
      }
      ts.forEachChild(node, visit)
    }
    visit(sf)

    // 2) compiler errors on added lines that are attributable to a third-party symbol
    for (const d of program.getSemanticDiagnostics(sf)) {
      if (d.start === undefined) continue
      const line = lineOf(d.start)
      if (f.lines && !f.lines.has(line)) continue
      const msg = ts.flattenDiagnosticMessageText(d.messageText, ' ')
      let node = (function find(n) { let hit = null; ts.forEachChild(n, (c) => { if (!hit && c.getStart(sf) <= d.start && d.start < c.getEnd()) hit = find(c) || c }); return hit })(sf)
      let pkg = null
      let api = node ? node.getText(sf) : '?'
      if ([2305, 2307, 2614, 2724].includes(d.code)) {
        let n = node
        while (n && !ts.isImportDeclaration(n)) n = n.parent
        const spec = n && ts.isStringLiteral(n.moduleSpecifier) ? n.moduleSpecifier.text : null
        if (spec && !spec.startsWith('.')) {
          pkg = { name: spec.startsWith('@') ? spec.split('/').slice(0, 2).join('/') : spec.split('/')[0] }
          api = node && (ts.isIdentifier(node) || ts.isImportSpecifier(node)) ? node.getText(sf) : spec
        }
      } else if ([2339, 2551].includes(d.code)) {
        let n = node
        while (n && !ts.isPropertyAccessExpression(n)) n = n.parent
        if (n) {
          const t = checker.getTypeAtLocation(n.expression)
          const s = t.getSymbol() || t.aliasSymbol
          const decl = s && thirdPartyDecl(s.declarations)
          if (decl) { pkg = pkgOf(decl.getSourceFile().fileName); api = `${checker.typeToString(t)}.${n.name.text}` }
        }
      } else if ([2554, 2555, 2556, 2345, 2769, 2559, 2353].includes(d.code)) {
        let n = node
        while (n && !ts.isCallExpression(n) && !ts.isNewExpression(n)) n = n.parent
        if (n) {
          const sig = checker.getResolvedSignature(n)
          const decl = (sig && sig.declaration) || null
          const callee = n.expression
          const s = checker.getSymbolAtLocation(ts.isPropertyAccessExpression(callee) ? callee.name : callee)
          const td = (decl && decl.getSourceFile && decl.getSourceFile().fileName.includes(NM)) ? decl : (s && thirdPartyDecl(s.declarations))
          if (td) { pkg = pkgOf(td.getSourceFile().fileName); api = s ? qualName(checker, s) : callee.getText(sf) }
        }
      }
      if (pkg) push({ file: f.rel, line, kind: 'error', code: d.code, api, message: `TS${d.code}: ${msg}`, package: pkg.name, version: pkg.version || null })
    }
  }
  process.stdout.write(JSON.stringify(unreadable.length ? { findings, unreadable } : { findings }))
}

main().catch((e) => { process.stdout.write(JSON.stringify({ findings: [], internal_error: true, error: String(e && e.stack || e) })) })
