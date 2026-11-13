#!/usr/bin/env node
// VeriCode TypeScript compiler-API checker.
// stdin: {"projectRoot": "...", "module": "zod", "name": "ZodString", "member": "min", "args": ["'3'"]}
// stdout: JSON report. Uses the project's own node_modules for resolution and type information, and
// VeriCode's pinned TypeScript (tools/ts-checker) so user projects never need TypeScript installed.
'use strict'
const path = require('path')
const fs = require('fs')
const ts = require('typescript')

function readStdin() {
  return new Promise((res) => { let d = ''; process.stdin.on('data', (c) => (d += c)); process.stdin.on('end', () => res(d)) })
}

function pkgVersion(file) {
  let dir = path.dirname(file)
  for (let i = 0; i < 12 && dir !== path.dirname(dir); i++) {
    const pj = path.join(dir, 'package.json')
    if (fs.existsSync(pj)) {
      try { const d = JSON.parse(fs.readFileSync(pj, 'utf8')); if (d.name && d.version) return { name: d.name, version: d.version } } catch { /* ignore */ }
    }
    dir = path.dirname(dir)
  }
  return null
}

function deprecatedOf(decls) {
  for (const d of decls || []) {
    for (const tag of ts.getJSDocTags(d)) {
      if (tag.tagName.text === 'deprecated') return (ts.getTextOfJSDocComment(tag.comment) || 'marked @deprecated').trim()
    }
  }
  return null
}

function describeSignatures(checker, sigs, node) {
  return sigs.map((sig) => {
    const params = sig.getParameters().map((p) => {
      const decl = p.valueDeclaration || (p.declarations || [])[0]
      const optional = !!(decl && (decl.questionToken || decl.initializer || (ts.isParameter(decl) && checker.isOptionalParameter(decl))))
      const rest = !!(decl && decl.dotDotDotToken)
      return { name: p.getName(), optional, rest, type: checker.typeToString(checker.getTypeOfSymbolAtLocation(p, decl || node)) }
    })
    const required = params.filter((p) => !p.optional && !p.rest).length
    return {
      text: checker.signatureToString(sig),
      params,
      min_args: required,
      max_args: params.some((p) => p.rest) ? null : params.length,
      return_type: checker.typeToString(sig.getReturnType()),
      type_params: (sig.getTypeParameters() || []).map((tp) => ({ name: tp.symbol.getName(), constraint: tp.getConstraint() ? checker.typeToString(tp.getConstraint()) : null })),
      deprecated: deprecatedOf([sig.getDeclaration()].filter(Boolean)),
    }
  })
}

async function main() {
  const req = JSON.parse(await readStdin())
  // TypeScript hands the host normalised '/' file names (D:/x/y.ts on Windows): key in-memory files the same way
  const root = ts.normalizePath(path.resolve(req.projectRoot))
  const mod = req.module
  const name = req.name || ''
  const member = req.member || ''
  const isDefault = name === 'default'
  const local = '__vc_sym'
  const importLine = !name ? `import * as ${local} from ${JSON.stringify(mod)};`
    : isDefault ? `import ${local} from ${JSON.stringify(mod)};`
    : `import { ${name} as ${local}${/^[A-Za-z_$][\w$]*$/.test(name) ? ', ' + name : ''} } from ${JSON.stringify(mod)};`
  const probe = ts.normalizePath(path.join(root, '__vericode_probe__.ts'))
  const callFile = ts.normalizePath(path.join(root, '__vericode_call__.ts'))
  let callSrc = null
  if (Array.isArray(req.args)) {
    const args = req.args.join(', ')
    callSrc = `${importLine}\ndeclare const __inst: any;\n`
    if (member) {
      // instance member of a class (or static member / namespace member)
      // class -> instance type; namespace/object export (e.g. zod's `z`) -> its own type. `infer` avoids the
      // InstanceType<> constraint error (TS2344) on non-constructors. Member may be a path: coerce.number
      callSrc += `declare const __obj: typeof ${local} extends abstract new (...a: any) => infer I ? I : typeof ${local};\n__obj.${member}(${args});\n`
    } else {
      callSrc += `(${local} as any) && 0; ${local}(${args});\n`
    }
  }
  const files = { [probe]: `${importLine}\nexport const __vc_ref = ${local};\n` }
  if (callSrc) files[callFile] = callSrc
  const options = {
    noEmit: true, strict: true, skipLibCheck: true, esModuleInterop: true, allowSyntheticDefaultImports: true,
    target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ESNext, moduleResolution: ts.ModuleResolutionKind.Bundler,
    resolveJsonModule: true, types: [], baseUrl: root,
  }
  const host = ts.createCompilerHost(options)
  const orig = host.getSourceFile.bind(host)
  const mem = (f) => files[ts.normalizePath(f)]
  host.getSourceFile = (f, lang) => (mem(f) !== undefined ? ts.createSourceFile(f, mem(f), lang, true) : orig(f, lang))
  const fe = host.fileExists.bind(host)
  host.fileExists = (f) => mem(f) !== undefined || fe(f)
  const rf = host.readFile.bind(host)
  host.readFile = (f) => (mem(f) !== undefined ? mem(f) : rf(f))
  host.getCurrentDirectory = () => root
  const program = ts.createProgram(Object.keys(files), options, host)
  const checker = program.getTypeChecker()
  const sf = program.getSourceFile(probe)
  const imp = sf && sf.statements.find(ts.isImportDeclaration)
  if (!imp) return { module: mod, name, member, internal_error: true, error: `checker could not load its probe file (${probe})` }
  const out = { module: mod, name, member, resolved: false, found: false }
  const resolution = ts.resolveModuleName(mod, probe, options, host)
  const rm = resolution.resolvedModule
  if (!rm) { out.error = `cannot resolve module '${mod}' from ${root}`; return out }
  out.resolved = true
  out.resolved_file = path.relative(root, rm.resolvedFileName)
  out.package = pkgVersion(rm.resolvedFileName)
  const modSym = checker.getSymbolAtLocation(imp.moduleSpecifier)
  if (!modSym) { out.error = 'module has no type information'; return out }
  const exportsList = checker.getExportsOfModule(modSym).map((s) => s.getName())
  out.export_count = exportsList.length
  out.has_default_export = exportsList.includes('default')
  if (!name) { out.found = true; out.kind = 'module'; return out }
  if (!exportsList.includes(name)) {
    out.found = false
    out.export_kind = 'none'
    const lower = name.toLowerCase()
    out.similar_exports = exportsList.filter((e) => e.toLowerCase().includes(lower.slice(0, 4))).slice(0, 8)
    return out
  }
  out.export_kind = isDefault ? 'default' : 'named'
  let sym = checker.getExportsOfModule(modSym).find((s) => s.getName() === name)
  if (sym.flags & ts.SymbolFlags.Alias) sym = checker.getAliasedSymbol(sym)
  const decl = (sym.declarations || [])[0]
  out.kind = sym.flags & ts.SymbolFlags.Class ? 'class' : sym.flags & ts.SymbolFlags.Function ? 'function'
    : sym.flags & ts.SymbolFlags.Interface ? 'interface' : sym.flags & ts.SymbolFlags.TypeAlias ? 'type'
    : sym.flags & ts.SymbolFlags.Enum ? 'enum' : sym.flags & ts.SymbolFlags.Module ? 'namespace' : 'variable'
  if (decl) {
    const df = decl.getSourceFile()
    out.location = `${path.relative(root, df.fileName)}:${df.getLineAndCharacterOfPosition(decl.getStart()).line + 1}`
  }
  out.deprecated = deprecatedOf(sym.declarations)
  let target = sym
  let type = decl ? checker.getTypeOfSymbolAtLocation(sym, decl) : checker.getDeclaredTypeOfSymbol(sym)
  if (member) {
    const instType = sym.flags & (ts.SymbolFlags.Class | ts.SymbolFlags.Interface) ? checker.getDeclaredTypeOfSymbol(sym) : null
    const segs = member.split('.')
    const access = [] // accessor path for the call check; "()" inserted where we stepped through a call's result
    let prop = null, pd = null
    for (let i = 0; i < segs.length; i++) {
      const seg = segs[i]
      prop = i === 0 && instType ? checker.getPropertyOfType(instType, seg) : null
      if (!prop) prop = checker.getPropertyOfType(type, seg) // static / namespace / object member
      if (!prop && i > 0 && type.getConstructSignatures().length) {
        // class reached through a namespace (z.ZodSchema.parse): instance member, look on the instance type
        const inst = checker.getReturnTypeOfSignature(type.getConstructSignatures()[0])
        const ip = checker.getPropertyOfType(inst, seg)
        if (ip) { type = inst; prop = ip; out.instance_member = true }
      }
      if (!prop && (i > 0 || !instType) && type.getCallSignatures().length) {
        // chained API (z.coerce.number().int()): the member lives on the previous call's return type
        const sig0 = type.getCallSignatures()[0]
        type = checker.getReturnTypeOfSignature(sig0)
        const nreq = typeof sig0.minArgumentCount === 'number' ? sig0.minArgumentCount : 0
        const callArgs = '(' + Array(nreq).fill('null as any').join(', ') + ')'
        if (access.length) access[access.length - 1] += callArgs
        else out.call_root = callArgs
        out.chained_call = true
        prop = checker.getPropertyOfType(type, seg)
      }
      access.push(seg)
      if (!prop) {
        out.found = false; out.member_found = false
        out.error = `${[name].concat(segs.slice(0, i)).join('.')} has no member '${seg}'`
        return out
      }
      pd = (prop.declarations || [])[0]
      type = checker.getTypeOfSymbolAtLocation(prop, pd || imp)
    }
    target = prop
    out.member_access = access.join('.')
    out.member_found = true
    out.deprecated = deprecatedOf(prop.declarations)
    if (pd) {
      const pf = pd.getSourceFile()
      out.location = `${path.relative(root, pf.fileName)}:${pf.getLineAndCharacterOfPosition(pd.getStart()).line + 1}`
    }
  }
  out.found = true
  out.signatures = describeSignatures(checker, type.getCallSignatures(), decl || imp)
  out.construct_signatures = member ? [] : describeSignatures(checker, type.getConstructSignatures(), decl || imp)
  if (!out.deprecated) {
    const sigDep = out.signatures.find((s) => s.deprecated)
    if (sigDep && out.signatures.every((s) => s.deprecated)) out.deprecated = sigDep.deprecated
  }
  let prog = program
  if (callSrc && out.chained_call && out.member_access) {
    // root call result: take its return type without inventing call arguments
    callSrc = out.call_root
      ? callSrc.replace(`__obj.${member}(`, `__obj${out.call_root}.${out.member_access}(`)
      : callSrc.replace(`__obj.${member}(`, `__obj.${out.member_access}(`)
    files[callFile] = callSrc
    prog = ts.createProgram(Object.keys(files), options, host, program)
  }
  if (callSrc) {
    const cf = prog.getSourceFile(callFile)
    if (!cf) return { ...out, internal_error: true, error: `checker could not load its call file (${callFile})` }
    const diags = ts.getPreEmitDiagnostics(prog, cf).filter((d) => d.file && ts.normalizePath(d.file.fileName) === callFile)
    out.call_check = {
      source: callSrc.split('\n').slice(-2).join('\n').trim(),
      diagnostics: diags.map((d) => ({ code: d.code, message: ts.flattenDiagnosticMessageText(d.messageText, ' ') })),
    }
    out.call_check.ok = out.call_check.diagnostics.length === 0
  }
  void target
  return out
}

main().then((o) => process.stdout.write(JSON.stringify(o))).catch((e) => { process.stdout.write(JSON.stringify({ internal_error: true, error: String(e && e.stack || e) })); process.exitCode = 0 })
