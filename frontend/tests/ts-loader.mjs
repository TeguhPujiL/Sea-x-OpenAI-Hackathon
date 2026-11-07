// Test-only TypeScript loader using the project's existing dependency; no manifest changes.
import { readFile, access } from "node:fs/promises";
import ts from "typescript";
export async function resolve(specifier, context, next) {
  if (specifier.startsWith(".") && context.parentURL) {
    for (const extension of [".ts", ".tsx"]) {
      const url = new URL(specifier + extension, context.parentURL);
      try { await access(url); return { url: url.href, shortCircuit: true }; } catch { /* Try normal resolution. */ }
    }
  }
  return next(specifier, context);
}
export async function load(url, context, next) {
  if (/\.tsx?$/.test(url)) {
    const source = await readFile(new URL(url), "utf8");
    const result = ts.transpileModule(source, { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ESNext, jsx: ts.JsxEmit.ReactJSX }, fileName: new URL(url).pathname });
    return { format: "module", source: result.outputText, shortCircuit: true };
  }
  return next(url, context);
}
