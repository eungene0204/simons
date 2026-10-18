"use client";

import { FormEvent, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useQueryClient } from "@tanstack/react-query";
import { CaretDown, CircleNotch } from "phosphor-react";
import { t, getLocale } from "@/lib/i18n";
import { categories, reasons } from "@/lib/board/rules";

type Entry = { id: string; title?: string; category?: string; nickname: string; body: string; createdAt: string; _count?: { comments: number } };
type Result = { posts?: Entry[]; post?: Entry; comments?: Entry[]; count?: number; page?: number; hasNext?: boolean; reports?: { id: string; postId?: string; commentId?: string; reason: string; post?: Entry; comment?: Entry }[] };
const control = "rounded-xl border border-white/15 bg-transparent p-3 text-white focus:outline-none focus:ring-2 focus:ring-[var(--chat-accent)]";
const button = control + " min-h-11 hover:bg-white/10 disabled:opacity-40";
function SavingIndicator() { return <span role="status" className="inline-flex items-center gap-2"><CircleNotch size={16} aria-hidden="true" className="animate-spin motion-reduce:animate-none" />{t("저장 중")}</span>; }

async function api(query = "", input?: Record<string, unknown>) {
  const response = await fetch("/api/board" + query, input ? { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(input) } : { cache: "no-store" });
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || t("저장 실패"));
  return data;
}

function Editor({ entry, postId, onDone, onCancel }: { entry?: Entry; postId?: string; onDone: (data: { id: string; status: string }) => void; onCancel: () => void }) {
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const values = Object.fromEntries(new FormData(event.currentTarget));
    if (new TextEncoder().encode(String(values.password)).length > 72) { setError(t("비밀번호는 UTF-8 72바이트 이내로 입력해 주세요.")); return; }
    setBusy(true); setError("");
    try { onDone(await api("", { ...values, action: entry ? "update" : "create", kind: postId ? "comment" : "post", postId, id: entry?.id })); }
    catch (failure) { setError((failure as Error).message); }
    finally { setBusy(false); }
  }
  return <form onSubmit={submit} className="space-y-4 border-t border-white/10 pt-5">
    <p className="text-sm text-[var(--text-label)]">{t("광고·음란물·혐오 및 차별 표현은 게시할 수 없습니다")}</p>
    <p className="text-sm text-[var(--text-label)]">{t("게시글과 댓글은 저장 직후 공개됩니다. 운영 원칙을 위반하는 콘텐츠는 저장되지 않습니다.")}</p>
    <p className="text-sm text-[var(--text-label)]">{t("제목 120자 · 닉네임 24자 · 본문 10,000자(댓글 2,000자) · 비밀번호 4~64자, UTF-8 72바이트 이내")}</p>
    {!postId && <><label className="block">{t("분류")}<span className="relative ml-3 inline-block align-middle"><select name="category" defaultValue={entry?.category || "자유"} className={control + " appearance-none pl-4 pr-10"}>{categories.map(category => <option className="bg-[var(--background)]" key={category}>{category}</option>)}</select><CaretDown aria-hidden="true" size={16} className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2" /></span></label>
      <label className="block">{t("제목")}<input name="title" required maxLength={120} defaultValue={entry?.title} className={control + " mt-2 w-full"} /></label></>}
    <label className="block">{t("닉네임")}<input name="nickname" maxLength={24} defaultValue={entry?.nickname} placeholder={t("익명")} className={control + " mt-2 w-full"} /></label>
    <label className="block">{t("본문")}<textarea name="body" required maxLength={postId ? 2000 : 10000} defaultValue={entry?.body} rows={postId ? 4 : 12} className={control + " mt-2 w-full"} /></label>
    <label className="block">{t("수정·삭제 비밀번호")}<input name="password" type="password" required minLength={4} maxLength={64} autoComplete="off" className={control + " mt-2 w-full"} /></label>
    <label className="hidden" aria-hidden="true">Website<input name="website" tabIndex={-1} autoComplete="off" /></label>
    {error && <p role="alert" className="text-[var(--error-red)]">{error}</p>}
    <div className="flex gap-3"><button disabled={busy} className={button}>{busy ? <SavingIndicator /> : t("저장")}</button><button type="button" className={button} onClick={onCancel}>{t("취소")}</button></div>
  </form>;
}

export default function Board() {
  const queryClient = useQueryClient();
  const [id, setId] = useState("");
  const [mode, setMode] = useState("list");
  const [data, setData] = useState<Result>({});
  const [query, setQuery] = useState("");
  const [search, setSearch] = useState("");
  const [category, setCategory] = useState("");
  const [page, setPage] = useState(1);
  const [commentPage, setCommentPage] = useState(1);
  const [version, setVersion] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [editing, setEditing] = useState<Entry>();
  const [action, setAction] = useState<{ entry: Entry; kind: string; type: string }>();
  const [busy, setBusy] = useState(false);
  const requestSequence = useRef(0);
  useEffect(() => {
    const sync = () => { const params = new URLSearchParams(location.search); setId(params.get("id") || ""); setMode(params.get("view") || "list"); setEditing(undefined); setAction(undefined); setCommentPage(1); };
    sync(); window.addEventListener("popstate", sync);
    return () => window.removeEventListener("popstate", sync);
  }, []);
  function navigate(nextId = "", view = "list") {
    history.pushState(null, "", "/board" + (nextId ? "?id=" + encodeURIComponent(nextId) : view !== "list" ? "?view=" + view : ""));
    setId(nextId); setMode(view); setEditing(undefined); setAction(undefined); setCommentPage(1); setError(""); setNotice("");
  }
  useEffect(() => {
    const sequence = ++requestSequence.current;
    if (mode === "new") { setLoading(false); return; }
    const params = new URLSearchParams(id ? { id, commentPage: String(commentPage) } : mode === "admin" ? { admin: "1", page: String(page) } : { q: query, category, page: String(page) });
    const queryKey = ["board", mode, id, query, category, page, commentPage, version];
    const cached = mode === "admin" ? undefined : queryClient.getQueryData<Result>(queryKey);
    if (cached) {
      setData(cached);
      setLoading(false);
      setError("");
    } else {
      setLoading(true);
      setError("");
      setData({});
    }
    const request = mode === "admin"
      ? api("?" + params)
      : queryClient.fetchQuery({ queryKey, queryFn: () => api("?" + params), staleTime: 2_000 });
    void request.then(result => {
      if (requestSequence.current !== sequence) return;
      setData(result);
      setError("");
    }).catch(failure => {
      if (requestSequence.current !== sequence) return;
      setError(failure.message);
    }).finally(() => { if (requestSequence.current === sequence) setLoading(false); });
    return () => { if (requestSequence.current === sequence) requestSequence.current += 1; };
  }, [id, mode, query, category, page, commentPage, version, queryClient]);
  function done(result: { id: string; status: string }) {
    if (mode === "new") navigate(result.id);
    setEditing(undefined); setVersion(value => value + 1);
    setNotice(t("저장되었습니다."));
  }
  function controls(entry: Entry, kind: string) {
    return <div className="flex flex-wrap gap-2 text-sm">
      <button className={button} onClick={() => { setEditing(entry); setAction(undefined); }}>{t("수정")}</button>
      <button className={button} onClick={() => setAction({ entry, kind, type: "delete" })}>{t("삭제")}</button>
      <button className={button} onClick={() => setAction({ entry, kind, type: "report" })}>{t("신고")}</button>
    </div>;
  }
  async function perform(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); if (!action) return;
    const values = Object.fromEntries(new FormData(event.currentTarget));
    setBusy(true); setError("");
    try {
      await api("", { ...values, id: action.entry.id, kind: action.kind, action: action.type });
      if (action.type === "delete" && action.kind === "post") navigate();
      setNotice(action.type === "report" ? t("신고가 접수되었습니다.") : t("삭제되었습니다."));
      setAction(undefined); setVersion(value => value + 1);
    } catch (failure) { setError((failure as Error).message); } finally { setBusy(false); }
  }
  function date(entry: Entry) { return new Date(entry.createdAt).toLocaleString(getLocale()); }
  return <main className="mx-auto max-w-5xl px-4 pb-20 pt-[calc(var(--top-menu-bar-height,80px)+32px)]">
    <div className="overflow-hidden rounded-2xl border border-white/[0.08] divide-y divide-white/[0.08]">
      <header className="flex flex-wrap items-center justify-between gap-4 p-5"><button onClick={() => navigate()}><h1 className="text-2xl font-black">{t("자유게시판")}</h1></button><div className="flex gap-3"><Link className={button} href="/">{t("홈")}</Link><button className={button} onClick={() => navigate("", "new")}>{t("글쓰기")}</button></div></header>
      <section className="space-y-5 p-5">
        {notice && <p role="status">{notice}</p>}
        {error && <div role="alert" className="text-[var(--error-red)]">{error} <button className={button} onClick={() => setVersion(value => value + 1)}>{t("다시 시도")}</button></div>}
        {mode === "new" ? <Editor onDone={done} onCancel={() => navigate()} /> : loading ? <p role="status" className="animate-pulse motion-reduce:animate-none">{t("불러오는 중")}</p> : mode === "admin" ? <>
          <h2 className="font-bold">{t("게시판 관리")}</h2>
          {(data.reports || []).map((report, index) => { const item = { entry: (report.post || report.comment)!, kind: report.postId ? "post" : "comment", reason: report.reason }; return <article key={report.id || index} className="space-y-3 border-t border-white/10 py-4">
            <p>{item.entry?.title} · {item.entry?.nickname}</p><p className="whitespace-pre-wrap break-words">{item.entry?.body}</p>{"reason" in item && <p>{String(item.reason)}</p>}
            <form className="flex flex-wrap gap-2" onSubmit={async event => {
              event.preventDefault(); const values = Object.fromEntries(new FormData(event.currentTarget)); setBusy(true);
              try { await api("", { ...values, action: "moderate", id: item.entry.id, kind: item.kind }); setVersion(value => value + 1); } catch (failure) { setError((failure as Error).message); } finally { setBusy(false); }
            }}><input aria-label={t("조치 사유")} name="reason" required maxLength={500} className={control} placeholder={t("조치 사유")} /><select name="status" className={control}><option value="PUBLIC">{t("승인")}</option><option value="HIDDEN">{t("숨김")}</option><option value="DELETED">{t("삭제")}</option></select><button disabled={busy} className={button}>{busy ? <SavingIndicator /> : t("적용")}</button></form>
          </article>; })}
          <div className="flex gap-3"><button className={button} disabled={page <= 1} onClick={() => setPage(page - 1)}>{t("이전")}</button><span>{page}</span><button className={button} onClick={() => setPage(page + 1)}>{t("다음")}</button></div>
        </> : id && data.post ? <>
          {editing?.id === id ? <Editor entry={editing} onDone={done} onCancel={() => setEditing(undefined)} /> : <article className="space-y-4">
            <p className="text-[var(--text-label)]">{data.post.category} · {data.post.nickname} · {date(data.post)}</p>
            <h2 className="break-words text-2xl font-black">{data.post.title}</h2><p className="whitespace-pre-wrap break-words">{data.post.body}</p>{controls(data.post, "post")}
          </article>}
          <h3 className="font-bold">{t("댓글")} ({data.count || 0})</h3>
          {(data.comments || []).map(comment => <article key={comment.id} className="space-y-3 border-t border-white/10 py-4">
            <p className="text-sm text-[var(--text-label)]">{comment.nickname} · {date(comment)}</p>
            {editing?.id === comment.id ? <Editor entry={comment} postId={id} onDone={done} onCancel={() => setEditing(undefined)} /> : <><p className="whitespace-pre-wrap break-words">{comment.body}</p>{controls(comment, "comment")}</>}
          </article>)}
          <div className="flex gap-3"><button className={button} disabled={commentPage <= 1} onClick={() => setCommentPage(commentPage - 1)}>{t("이전")}</button><span>{commentPage}</span><button className={button} disabled={commentPage * 30 >= (data.count || 0)} onClick={() => setCommentPage(commentPage + 1)}>{t("다음")}</button></div>
          <Editor key={version} postId={id} onDone={done} onCancel={() => navigate()} />
        </> : !id ? <>
          <form className="flex flex-wrap gap-3" onSubmit={event => { event.preventDefault(); setQuery(search); setPage(1); }}><input aria-label={t("제목·본문 검색")} value={search} onChange={event => setSearch(event.target.value)} maxLength={120} className={control + " min-w-0 flex-1"} placeholder={t("제목·본문 검색")} /><button className={button}>{t("검색")}</button></form>
          <div className="flex flex-wrap gap-2">{["", ...categories].map(value => <button key={value} aria-pressed={category === value} onClick={() => { setCategory(value); setPage(1); }} className={button + (category === value ? " bg-white/10" : "")}>{value ? t(value) : t("전체")}</button>)}</div>
          <p className="text-sm text-[var(--text-label)]">{t("최신순")}</p>
          {!data.posts?.length && <p>{query ? t("검색 결과가 없습니다.") : t("아직 게시글이 없습니다.")}</p>}
          <div className="divide-y divide-white/[0.08]">{data.posts?.map(post => <Link key={post.id} href={"/board?id=" + post.id} onClick={event => { event.preventDefault(); navigate(post.id); }} className="block space-y-2 py-4 hover:bg-white/[0.02]">
            <div className="flex gap-3"><span className="shrink-0 text-[var(--text-label)]">{t(post.category || "자유")}</span><span className="min-w-0 break-words font-bold">{post.title} <span className="text-[var(--chat-accent)]">[{post._count?.comments || 0}]</span></span></div>
            <p className="text-sm text-[var(--text-label)]">{post.nickname} · {date(post)}</p>
          </Link>)}</div>
          <div className="flex items-center gap-4"><button disabled={page <= 1} className={button} onClick={() => setPage(page - 1)}>{t("이전")}</button><span>{t("{0} 페이지", page)}</span><button disabled={!data.hasNext} className={button} onClick={() => setPage(page + 1)}>{t("다음")}</button></div>
        </> : null}
        {action && <form onSubmit={perform} className="space-y-3 rounded-xl border border-white/15 p-4"><h3>{action.type === "report" ? t("신고") : t("삭제")}</h3>
          {action.type === "report" ? <select name="reason" aria-label={t("신고 사유")} className={control}>{reasons.map(reason => <option className="bg-[var(--background)]" key={reason}>{reason}</option>)}</select> : <input aria-label={t("수정·삭제 비밀번호")} name="password" type="password" required minLength={4} maxLength={64} className={control} />}
          <div className="flex gap-3"><button disabled={busy} className={button}>{busy ? <SavingIndicator /> : t("확인")}</button><button type="button" className={button} onClick={() => setAction(undefined)}>{t("취소")}</button></div>
        </form>}
      </section>
    </div>
  </main>;
}
