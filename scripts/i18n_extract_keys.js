#!/usr/bin/env node
/*
 * i18n 키 추출 — 사전(lib/i18n/en.ts)에 있어야 할 한국어 원문을 모은다.
 *   1) t("…") 호출의 첫 인자(리터럴)              — 표시 지점에서 직접 번역
 *   2) 렌더 지점 t(x)로 번역되는 상수 파일의 한글 리터럴 — 칩·질문·라벨 맵(RENDER_SITE_FILES)
 * 출력: JSON [{ key, files: [...] }] (stdout). tests/i18n-coverage.test.ts와 같은 규칙을 쓴다.
 *
 * 사용: node scripts/i18n_extract_keys.js [--missing] > keys.json
 *   --missing: 사전에 없는 키만 출력
 */
const ts = require("typescript");
const fs = require("fs");
const path = require("path");

const ROOT = path.resolve(__dirname, "..");
const HANGUL = /[가-힣]/;

// 렌더 지점에서 t(value)로 번역되는 한국어 상수(칩·질문·라벨 맵)를 담은 파일.
// 여기 있는 파일은 모든 한글 문자열 리터럴을 키로 본다(비교식·정규식 조각은 사람이 걸러 낸다).
const RENDER_SITE_FILES = [
  "app/analytics/new/conversationDecision.ts",
  "app/analytics/new/deterministicConditionFlow.ts",
  "app/analytics/new/coachMessage.ts",
  "app/analytics/new/strategyItems.ts",
  "app/analytics/new/clarificationPresentation.ts",
  "app/analytics/new/backtestConfirmation.ts",
  "app/analytics/new/backtestReadiness.ts",
  "app/analytics/new/builderProgressPresentation.ts",
  "app/analytics/new/rollback.ts",
  "app/analytics/new/walkForwardStream.ts",
  "app/analytics/new/turnMessage.ts",
  "app/analytics/new/chatNavigation.ts",
  "app/analytics/new/page.tsx",
  "lib/strategy-summary.ts",
  "components/strategy/StrategyExampleTabs.tsx",
  "components/layout/TopNavigation.tsx",
  "components/layout/SettingsModal.tsx",
  "components/strategy/backtest/WalkForwardModal.tsx",
  "components/strategy/backtest/OptimizationPage.tsx",
  "components/strategy/backtest/BacktestDashboard.tsx",
  "components/strategy/backtest/XAIModal.tsx",
  "components/strategy/backtest/SavedValidationsModal.tsx",
  "components/strategy/backtest/QuantileGroupsSection.tsx",
  "components/strategy/backtest/RebalanceComparisonSection.tsx",
  "components/strategy/backtest/rebalanceComparison.ts",
  "components/virtual-account/DelistingRiskBanner.tsx",
  "components/strategy/StrategyAdvisorPanel.tsx",
  "components/research/ResearchTestConsole.tsx",
  "components/pricing/PricingPlans.tsx",
  "components/dashboard/RecentBacktestList.tsx",
  "components/dashboard/VirtualAccountList.tsx",
  "app/stock-order/page.tsx",
  "app/virtual-account/[id]/page.tsx",
  "app/analytics/templates/page.tsx",
  "components/layout/planUsageFormat.ts",
];

function walk(dir, acc) {
  for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
    const p = path.join(dir, e.name);
    if (e.isDirectory()) walk(p, acc);
    else if (/\.tsx?$/.test(e.name)) acc.push(p);
  }
  return acc;
}

function sourceFiles() {
  const all = [];
  for (const d of ["app", "components", "lib", "contexts"]) walk(path.join(ROOT, d), all);
  return all
    .map((p) => path.relative(ROOT, p))
    .filter(
      (f) =>
        !/\.test\.tsx?$/.test(f) &&
        !f.includes("__tests__") &&
        !f.includes("__fixtures__") &&
        !f.startsWith("lib/i18n/") &&
        !f.startsWith("components/admin/") &&
        !f.startsWith("app/console")
    );
}

function extract() {
  const keys = new Map(); // key -> Set(files)
  const add = (key, file) => {
    if (!HANGUL.test(key)) return;
    if (!keys.has(key)) keys.set(key, new Set());
    keys.get(key).add(file);
  };
  for (const rel of sourceFiles()) {
    const src = fs.readFileSync(path.join(ROOT, rel), "utf8");
    if (!HANGUL.test(src)) continue;
    const sf = ts.createSourceFile(rel, src, ts.ScriptTarget.Latest, true, rel.endsWith(".tsx") ? ts.ScriptKind.TSX : ts.ScriptKind.TS);
    const renderSite = RENDER_SITE_FILES.includes(rel);
    (function visit(node) {
      if (ts.isCallExpression(node) && ts.isIdentifier(node.expression) && node.expression.text === "t" && node.arguments.length > 0) {
        const a = node.arguments[0];
        if (ts.isStringLiteral(a) || ts.isNoSubstitutionTemplateLiteral(a)) add(a.text, rel);
      } else if (renderSite && (ts.isStringLiteral(node) || ts.isNoSubstitutionTemplateLiteral(node))) {
        // 비교식·정규식 인자·import 는 키가 아니다
        const p = node.parent;
        const isCompare = p && ts.isBinaryExpression(p) && [ts.SyntaxKind.EqualsEqualsEqualsToken, ts.SyntaxKind.ExclamationEqualsEqualsToken].includes(p.operatorToken.kind);
        const isImport = p && (ts.isImportDeclaration(p) || ts.isExportDeclaration(p));
        const isRegexArg = p && ts.isCallExpression(p) && ts.isPropertyAccessExpression(p.expression) && ["test", "match", "replace", "replaceAll", "includes", "startsWith", "endsWith", "indexOf", "split"].includes(p.expression.name.text);
        const isNewRegExp = p && ts.isNewExpression(p) && ts.isIdentifier(p.expression) && p.expression.text === "RegExp";
        if (!isCompare && !isImport && !isRegexArg && !isNewRegExp) add(node.text, rel);
      }
      ts.forEachChild(node, visit);
    })(sf);
  }
  return keys;
}

if (require.main === module) {
  const onlyMissing = process.argv.includes("--missing");
  const keys = extract();
  let en = {};
  if (onlyMissing) {
    // en.ts 를 파싱해 키 목록을 얻는다(모듈 로드 대신 정적 파싱 — TS 파일).
    const src = fs.readFileSync(path.join(ROOT, "lib/i18n/en.ts"), "utf8");
    const sf = ts.createSourceFile("en.ts", src, ts.ScriptTarget.Latest, true);
    (function visit(node) {
      if (ts.isPropertyAssignment(node) && (ts.isStringLiteral(node.name) || ts.isNoSubstitutionTemplateLiteral(node.name))) en[node.name.text] = true;
      ts.forEachChild(node, visit);
    })(sf);
  }
  const out = [];
  for (const [key, files] of keys) {
    if (onlyMissing && en[key]) continue;
    out.push({ key, files: Array.from(files) });
  }
  out.sort((a, b) => a.files[0].localeCompare(b.files[0]) || a.key.localeCompare(b.key));
  process.stdout.write(JSON.stringify(out, null, 0));
}

module.exports = { extract, RENDER_SITE_FILES };
