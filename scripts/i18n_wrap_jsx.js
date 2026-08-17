#!/usr/bin/env node
/*
 * i18n codemod — JSX 표시 문자열을 t()로 감싼다.
 *
 * 다루는 것(표시 전용 컨텍스트만):
 *   - JSX 텍스트 자식(한글 포함)          <p>총 {n}회</p>        → <p>{t("총 {0}회", n)}</p>
 *   - JSX 속성 문자열(한글 포함)          placeholder="…"        → placeholder={t("…")}
 *   - JSX 표현식 안의 문자열/템플릿 리터럴 {a ? "…" : `…${x}`}   → {a ? t("…") : t("… {0}", x)}
 * 다루지 않는 것(리포트만): 비교 대상 문자열, 객체 키, 호출 인자, 모듈 상수의 라벨 등 —
 * 백엔드 프로토콜 값일 수 있어 사람이 판단한다.
 *
 * 사용: node scripts/i18n_wrap_jsx.js [--dry] [--report] [files...]
 *   파일을 주지 않으면 app/ components/ lib/ contexts/ 아래 클라이언트 파일 전체.
 */
const ts = require("typescript");
const fs = require("fs");
const path = require("path");

const ROOT = path.resolve(__dirname, "..");
const HANGUL = /[가-힣]/;
const IMPORT_LINE = 'import { t } from "@/lib/i18n";';

const args = process.argv.slice(2);
const DRY = args.includes("--dry");
const REPORT = args.includes("--report");
// --literals: JSX 밖의 "표시 전용으로 판정 가능한" 문맥도 감싼다(아래 displayContextNonJsx).
const LITERALS = args.includes("--literals");
// --all: 표시 전용으로 검토가 끝난 파일에 한해, 비교/키/case/모듈 최상위를 제외한 모든 한글
// 리터럴을 감싼다(파일을 명시했을 때만 의미가 있다).
const ALL = args.includes("--all");
const explicitFiles = args.filter((a) => !a.startsWith("--"));

const EXCLUDE_ATTRS = new Set([
  "key", "value", "defaultValue", "name", "id", "href", "src", "type", "role", "lang",
  "content", "htmlFor", "className", "style", "target", "rel", "action", "method",
]);

function walk(dir, acc) {
  for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
    const p = path.join(dir, e.name);
    if (e.isDirectory()) walk(p, acc);
    else if (/\.tsx?$/.test(e.name)) acc.push(p);
  }
  return acc;
}

function defaultFiles() {
  const all = [];
  for (const d of ["app", "components", "lib", "contexts"]) walk(path.join(ROOT, d), all);
  return all
    .map((p) => path.relative(ROOT, p))
    .filter(
      (f) =>
        !/\.test\.tsx?$/.test(f) &&
        !f.includes("__tests__") &&
        !f.includes("__fixtures__") &&
        !f.startsWith("app/api/") &&
        !f.startsWith("lib/server/") &&
        !f.startsWith("lib/i18n/") &&
        f !== "lib/scheduler.ts" &&
        !f.startsWith("components/admin/") &&
        !f.startsWith("app/console")
    )
    .filter((f) => HANGUL.test(fs.readFileSync(path.join(ROOT, f), "utf8")));
}

const ENTITIES = {
  nbsp: " ", amp: "&", lt: "<", gt: ">", quot: '"', apos: "'", middot: "·", hellip: "…",
  times: "×", rarr: "→", larr: "←", bull: "•", copy: "©", mdash: "—", ndash: "–", laquo: "«",
  raquo: "»", lsquo: "‘", rsquo: "’", ldquo: "“", rdquo: "”", deg: "°", plusmn: "±",
};
function decodeEntities(text) {
  let unknown = false;
  const out = text.replace(/&(#x[0-9a-fA-F]+|#\d+|[a-zA-Z]+);/g, (m, body) => {
    if (body[0] === "#") {
      const code = body[1] === "x" || body[1] === "X" ? parseInt(body.slice(2), 16) : parseInt(body.slice(1), 10);
      return String.fromCodePoint(code);
    }
    if (ENTITIES[body] !== undefined) return ENTITIES[body];
    unknown = true;
    return m;
  });
  return { text: out, unknown };
}

// Babel의 cleanJSXElementLiteralChild와 동일한 규칙으로 렌더 텍스트를 계산한다.
function renderedJsxText(raw) {
  const lines = raw.split(/\r\n|\n|\r/);
  let lastNonEmptyLine = 0;
  for (let i = 0; i < lines.length; i++) if (/[^ \t]/.test(lines[i])) lastNonEmptyLine = i;
  let str = "";
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    const isFirstLine = i === 0;
    const isLastLine = i === lines.length - 1;
    const isLastNonEmptyLine = i === lastNonEmptyLine;
    let trimmed = line.replace(/\t/g, " ");
    if (!isFirstLine) trimmed = trimmed.replace(/^[ ]+/, "");
    if (!isLastLine) trimmed = trimmed.replace(/[ ]+$/, "");
    if (trimmed) {
      if (!isLastNonEmptyLine) trimmed += " ";
      str += trimmed;
    }
  }
  return str;
}

function q(s) {
  return JSON.stringify(s);
}

function containsJsx(node) {
  let found = false;
  (function visit(n) {
    if (found) return;
    if (ts.isJsxElement(n) || ts.isJsxSelfClosingElement(n) || ts.isJsxFragment(n)) { found = true; return; }
    ts.forEachChild(n, visit);
  })(node);
  return found;
}

function isTCall(node) {
  return ts.isCallExpression(node) && ts.isIdentifier(node.expression) && node.expression.text === "t";
}

const COMPARISON = new Set([
  ts.SyntaxKind.EqualsEqualsEqualsToken, ts.SyntaxKind.ExclamationEqualsEqualsToken,
  ts.SyntaxKind.EqualsEqualsToken, ts.SyntaxKind.ExclamationEqualsToken,
]);
const DISPLAY_LOGICAL = new Set([
  ts.SyntaxKind.AmpersandAmpersandToken, ts.SyntaxKind.BarBarToken, ts.SyntaxKind.QuestionQuestionToken,
  ts.SyntaxKind.PlusToken,
]);

// 리터럴에서 위로 올라가며 JsxExpression(표시 컨텍스트)에 닿는지 판정한다.
// 닿기 전에 비교식·호출 인자·객체/배열 리터럴 등을 만나면 표시 컨텍스트가 아니다.
function displayContext(node) {
  let child = node;
  let n = node.parent;
  while (n) {
    if (ts.isJsxExpression(n)) {
      // <style jsx>{`…`}</style> — styled-jsx는 자식이 리터럴이어야 컴파일된다(t() 호출로 바꾸면
      // next-swc-loader "failed to process"). CSS 주석의 한글 때문에 잡히므로 제외한다.
      const el = n.parent;
      if (el && ts.isJsxElement(el) && el.openingElement.tagName.getText() === "style") return null;
      return "jsx";
    }
    if (ts.isJsxAttribute(n)) return "attr";
    if (ts.isParenthesizedExpression(n)) { child = n; n = n.parent; continue; }
    if (ts.isConditionalExpression(n)) {
      if (n.condition === child) return null;
      child = n; n = n.parent; continue;
    }
    if (ts.isBinaryExpression(n)) {
      if (COMPARISON.has(n.operatorToken.kind)) return null;
      if (!DISPLAY_LOGICAL.has(n.operatorToken.kind)) return null;
      child = n; n = n.parent; continue;
    }
    if (isTCall(n)) return null;
    return null;
  }
  return null;
}

const DISPLAY_KEYS = new Set([
  "label", "title", "description", "message", "text", "placeholder", "subtitle", "hint", "tooltip",
  "summary", "caption", "note", "helper", "detail", "heading", "body", "example", "headline",
  "sublabel", "subLabel", "emptyText", "buttonText", "confirmText", "cancelText", "errorMessage",
  "successMessage", "warning", "notice", "reason", "question", "answer", "unit", "prefix", "suffix",
  "shortLabel", "longLabel", "ariaLabel", "eyebrow", "badge", "sub", "desc", "definition", "formula",
  "guideline", "explanation", "labelText", "helpText", "descriptionText", "titleText", "info",
]);
const DISPLAY_VAR = /(label|title|text|message|msg|desc|hint|caption|placeholder|summary|tooltip|error|warning|notice|reason|heading|body|explanation|question|answer|status|name)$/i;
const DISPLAY_SETTER = /^(set(?:[A-Z]\w*)?(Error|Message|Msg|Toast|Notice|Status|Label|Text|Hint|Title|Warning|Feedback|Result|Reason|Description|Note|Info|Placeholder|Summary)|alert|confirm|showToast|toast|notify|pushLog|addLog|appendLog|log)$/;
const DISPLAY_FUNC = /(label|text|title|format|describe|description|message|caption|hint|summary|reason|copy|tooltip|explain|name|status|badge|heading|line|sentence|phrase|note|render|display|present|humanize|verbalize|wording|prompt)/i;

function enclosingFunction(node) {
  let n = node.parent;
  while (n) {
    if (ts.isFunctionLike(n)) return n;
    n = n.parent;
  }
  return null;
}
function functionName(fn) {
  if (!fn) return "";
  if (fn.name && ts.isIdentifier(fn.name)) return fn.name.text;
  const p = fn.parent;
  if (p && ts.isVariableDeclaration(p) && ts.isIdentifier(p.name)) return p.name.text;
  if (p && ts.isPropertyAssignment(p) && ts.isIdentifier(p.name)) return p.name.text;
  return "";
}

// JSX 밖 표시 문맥 판정 — 조건식/괄호/논리연산을 거슬러 올라가 앵커를 보고 결정한다.
// 함수 밖(모듈 최상위)이면 절대 감싸지 않는다(t()는 렌더 시점에만).
function displayContextNonJsx(node) {
  if (!enclosingFunction(node)) return null;
  if (ALL) return allContext(node);
  let child = node;
  let n = node.parent;
  while (n) {
    if (ts.isParenthesizedExpression(n) || ts.isAsExpression(n) || ts.isSatisfiesExpression?.(n)) { child = n; n = n.parent; continue; }
    if (ts.isConditionalExpression(n)) {
      if (n.condition === child) return null;
      child = n; n = n.parent; continue;
    }
    if (ts.isBinaryExpression(n)) {
      if (COMPARISON.has(n.operatorToken.kind)) return null;
      if (!DISPLAY_LOGICAL.has(n.operatorToken.kind)) return null;
      child = n; n = n.parent; continue;
    }
    if (ts.isPropertyAssignment(n)) {
      if (n.initializer !== child) return null;
      const key = ts.isIdentifier(n.name) || ts.isStringLiteral(n.name) ? n.name.text : "";
      return DISPLAY_KEYS.has(key) ? "prop" : null;
    }
    if (ts.isVariableDeclaration(n)) {
      if (n.initializer !== child || !ts.isIdentifier(n.name)) return null;
      return DISPLAY_VAR.test(n.name.text) ? "var" : null;
    }
    if (ts.isReturnStatement(n) || ts.isArrowFunction(n)) {
      if (ts.isArrowFunction(n) && n.body !== child) return null;
      const fn = ts.isArrowFunction(n) ? n : enclosingFunction(n);
      return DISPLAY_FUNC.test(functionName(fn)) ? "return" : null;
    }
    if (ts.isCallExpression(n)) {
      if (!n.arguments.includes(child)) return null;
      const callee = n.expression;
      const name = ts.isIdentifier(callee) ? callee.text : ts.isPropertyAccessExpression(callee) ? callee.name.text : "";
      // t("…{0}…", cond ? "가" : "나") — 치환 인자의 한글 리터럴도 표시 문자열이다.
      if (name === "t") return n.arguments[0] !== child ? "targ" : null;
      return DISPLAY_SETTER.test(name) ? "call" : null;
    }
    if (ts.isNewExpression(n)) {
      const name = ts.isIdentifier(n.expression) ? n.expression.text : "";
      return /Error$/.test(name) && n.arguments && n.arguments[0] === child ? "error" : null;
    }
    if (ts.isBinaryExpression(n) && n.operatorToken.kind === ts.SyntaxKind.EqualsToken) {
      // 대입: 왼쪽 식별자 이름으로 판정
      if (n.right !== child) return null;
      const name = ts.isIdentifier(n.left) ? n.left.text : ts.isPropertyAccessExpression(n.left) ? n.left.name.text : "";
      return DISPLAY_VAR.test(name) ? "assign" : null;
    }
    return null;
  }
  return null;
}

function allContext(node) {
  let child = node;
  let n = node.parent;
  while (n) {
    if (ts.isParenthesizedExpression(n) || ts.isAsExpression(n)) { child = n; n = n.parent; continue; }
    if (ts.isConditionalExpression(n)) { if (n.condition === child) return null; child = n; n = n.parent; continue; }
    if (ts.isBinaryExpression(n)) {
      if (COMPARISON.has(n.operatorToken.kind)) return null;
      child = n; n = n.parent; continue;
    }
    if (ts.isPropertyAssignment(n) && n.name === child) return null;
    if (ts.isCaseClause(n)) return null;
    if (ts.isImportDeclaration(n) || ts.isExportDeclaration(n)) return null;
    if (ts.isCallExpression(n)) {
      const callee = n.expression;
      const name = ts.isPropertyAccessExpression(callee) ? callee.name.text : ts.isIdentifier(callee) ? callee.text : "";
      if (name === "t" && n.arguments[0] === child) return null;
      if (["includes", "startsWith", "endsWith", "indexOf", "test", "match", "replace", "split", "get", "has"].includes(name)) return null;
      return "all";
    }
    if (ts.isElementAccessExpression(n) && n.argumentExpression === child) return null;
    return "all";
  }
  return null;
}

function processFile(rel) {
  const file = path.join(ROOT, rel);
  let src = fs.readFileSync(file, "utf8");
  if (src.includes("i18n-ignore-file")) return { rel, edits: 0, report: [] };
  const report = [];
  let totalEdits = 0;
  for (let pass = 0; pass < 6; pass++) {
    const sf = ts.createSourceFile(file, src, ts.ScriptTarget.Latest, true, rel.endsWith(".tsx") ? ts.ScriptKind.TSX : ts.ScriptKind.TS);
    const edits = []; // {start,end,text,kind}
    const skipped = [];
    let tConflict = false;

    function visit(node) {
      // t 식별자 충돌 검사
      if ((ts.isVariableDeclaration(node) || ts.isParameter(node) || ts.isFunctionDeclaration(node)) && node.name && ts.isIdentifier(node.name) && node.name.text === "t") {
        tConflict = true;
      }
      if (ts.isJsxElement(node) || ts.isJsxFragment(node)) {
        handleChildren(node.children);
      } else if (ts.isJsxAttribute(node) && node.initializer && ts.isStringLiteral(node.initializer)) {
        const lit = node.initializer;
        if (HANGUL.test(lit.text)) {
          const attrName = node.name.getText();
          if (EXCLUDE_ATTRS.has(attrName) || attrName.startsWith("data-")) {
            skipped.push(`attr:${attrName} ${q(lit.text)}`);
          } else {
            const { text, unknown } = decodeEntities(lit.text);
            if (unknown) skipped.push(`attr-entity ${q(lit.text)}`);
            else edits.push({ start: lit.getStart(), end: lit.getEnd(), text: `{t(${q(text)})}`, kind: "attr" });
          }
        }
      } else if (ts.isStringLiteral(node) || ts.isNoSubstitutionTemplateLiteral(node)) {
        if (HANGUL.test(node.text) && !(node.parent && ts.isJsxAttribute(node.parent))) {
          const ctx = displayContext(node) || (LITERALS ? displayContextNonJsx(node) : null);
          if (ctx) {
            edits.push({ start: node.getStart(), end: node.getEnd(), text: `t(${q(node.text)})`, kind: "lit" });
          } else if (!isInsideTCall(node)) {
            skipped.push(`literal ${q(node.text)} @${lineOf(sf, node)}`);
          }
        }
      } else if (ts.isTemplateExpression(node)) {
        const raw = node.getText();
        // 리터럴 부분(head/middle/tail)에 한글이 있을 때만 — 표현식 안의 비교 문자열은 무관하다.
        const literalText = node.head.text + node.templateSpans.map((s) => s.literal.text).join("");
        if (HANGUL.test(literalText)) {
          const ctx = displayContext(node) || (LITERALS ? displayContextNonJsx(node) : null);
          const spans = node.templateSpans;
          const anyJsx = spans.some((s) => containsJsx(s.expression));
          if (ctx && !anyJsx) {
            let key = node.head.text;
            const argsText = [];
            spans.forEach((s, i) => {
              key += `{${i}}` + s.literal.text;
              argsText.push(s.expression.getText());
            });
            edits.push({ start: node.getStart(), end: node.getEnd(), text: `t(${q(key)}${argsText.length ? ", " + argsText.join(", ") : ""})`, kind: "tpl" });
          } else if (!isInsideTCall(node)) {
            skipped.push(`template ${q(raw.slice(0, 60))} @${lineOf(sf, node)}`);
          }
        }
      }
      ts.forEachChild(node, visit);
    }

    function isInsideTCall(node) {
      let n = node.parent;
      while (n) { if (isTCall(n)) return true; if (ts.isJsxExpression(n) || ts.isJsxElement(n)) return false; n = n.parent; }
      return false;
    }

    function handleChildren(children) {
      const list = children.slice();
      const texts = list.filter((c) => ts.isJsxText(c));
      if (!texts.some((c) => HANGUL.test(c.text))) return;
      const simple = list.every(
        (c) => ts.isJsxText(c) || (ts.isJsxExpression(c) && c.expression && !containsJsx(c.expression))
      );
      if (simple) {
        // 하나의 t() 호출로 병합
        let key = "";
        const argsText = [];
        let unknownEntity = false;
        list.forEach((c) => {
          if (ts.isJsxText(c)) {
            const rendered = renderedJsxText(c.getFullText());
            const { text, unknown } = decodeEntities(rendered);
            if (unknown) unknownEntity = true;
            key += text;
          } else {
            key += `{${argsText.length}}`;
            argsText.push(c.expression.getText());
          }
        });
        if (unknownEntity) { skipped.push(`entity ${q(key.slice(0, 60))}`); return; }
        // 첫 텍스트의 줄바꿈 포함 선행 공백·마지막 텍스트의 줄바꿈 포함 후행 공백은 바깥에 남긴다.
        const first = list[0], last = list[list.length - 1];
        // JsxText는 공백을 trivia로 취급해 getStart()가 건너뛰므로 pos/end(전체 범위)를 쓴다.
        let start = ts.isJsxText(first) ? first.pos : first.getStart();
        let end = last.end;
        if (ts.isJsxText(first)) {
          const m = first.getFullText().match(/^[ \t]*\r?\n[\s]*/);
          if (m) start = first.pos + m[0].length;
        }
        if (ts.isJsxText(last)) {
          const m = last.getFullText().match(/[\s]*\r?\n[ \t]*$/);
          if (m) end = last.end - m[0].length;
        }
        if (start >= end) return;
        // 선행/후행 공백을 잘라낸 만큼 key도 그 부분이 없어야 한다 — renderedJsxText가 이미 줄바꿈
        // 공백을 버리므로 일치한다.
        edits.push({ start, end, text: `{t(${q(key)}${argsText.length ? ", " + argsText.join(", ") : ""})}`, kind: "merge" });
      } else {
        // 요소 자식이 섞여 있음 — 한글 텍스트만 개별로 감싼다.
        for (const c of texts) {
          if (!HANGUL.test(c.text)) continue;
          const rendered = renderedJsxText(c.getFullText());
          const { text, unknown } = decodeEntities(rendered);
          if (unknown) { skipped.push(`entity ${q(text.slice(0, 60))}`); continue; }
          let start = c.pos, end = c.end;
          const full = c.getFullText();
          const lead = full.match(/^[ \t]*\r?\n[\s]*/);
          if (lead) start += lead[0].length;
          const trail = full.match(/[\s]*\r?\n[ \t]*$/);
          if (trail) end -= trail[0].length;
          if (start >= end) continue;
          edits.push({ start, end, text: `{t(${q(text)})}`, kind: "text" });
        }
      }
    }

    visit(sf);

    if (pass === 0) report.push(...skipped);
    if (edits.length === 0) break;
    if (pass === 5) { report.push("!! did not converge — inspect manually"); }
    if (tConflict) { report.push("!! identifier `t` already declared — skipped file"); return { rel, edits: 0, report }; }

    // 겹치는 편집은 안쪽(짧은 것) 우선 — 바깥은 다음 패스에서 다시 계산한다.
    edits.sort((a, b) => (a.end - a.start) - (b.end - b.start));
    const accepted = [];
    for (const e of edits) {
      if (accepted.some((a) => !(e.end <= a.start || e.start >= a.end))) continue;
      accepted.push(e);
    }
    accepted.sort((a, b) => b.start - a.start);
    for (const e of accepted) src = src.slice(0, e.start) + e.text + src.slice(e.end);
    totalEdits += accepted.length;
  }

  if (totalEdits > 0) {
    if (!/import\s*\{[^}]*\bt\b[^}]*\}\s*from\s*["']@\/lib\/i18n["']/.test(src)) {
      src = injectImport(src);
    }
    if (!DRY) fs.writeFileSync(file, src);
  }
  return { rel, edits: totalEdits, report };
}

function lineOf(sf, node) {
  return sf.getLineAndCharacterOfPosition(node.getStart()).line + 1;
}

function injectImport(src) {
  const sf = ts.createSourceFile("x.tsx", src, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
  let lastImportEnd = -1;
  for (const st of sf.statements) {
    if (ts.isImportDeclaration(st)) lastImportEnd = st.getEnd();
  }
  if (lastImportEnd >= 0) {
    return src.slice(0, lastImportEnd) + "\n" + IMPORT_LINE + src.slice(lastImportEnd);
  }
  // "use client" 지시문 뒤, 없으면 맨 앞
  const m = src.match(/^(["']use client["'];?\s*\n)/);
  if (m) return m[1] + IMPORT_LINE + "\n" + src.slice(m[1].length);
  return IMPORT_LINE + "\n" + src;
}

const files = explicitFiles.length ? explicitFiles : defaultFiles();
let total = 0;
for (const rel of files) {
  const r = processFile(rel);
  total += r.edits;
  if (r.edits || (REPORT && r.report.length)) {
    console.log(`${String(r.edits).padStart(4)} ${rel}`);
    if (REPORT) for (const line of r.report) console.log("       - " + line);
  }
}
console.log(`total edits: ${total}${DRY ? " (dry run)" : ""}`);
