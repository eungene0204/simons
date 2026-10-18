CREATE TABLE "BoardPost" (
 "id" TEXT PRIMARY KEY, "category" VARCHAR(10) NOT NULL DEFAULT '자유',
 "title" VARCHAR(120) NOT NULL CHECK (length(trim("title")) > 0),
 "nickname" VARCHAR(24) NOT NULL, "body" VARCHAR(10000) NOT NULL CHECK (length(trim("body")) > 0),
 "passwordHash" TEXT NOT NULL, "status" TEXT NOT NULL DEFAULT 'PUBLIC' CHECK ("status" IN ('PUBLIC','PENDING','HIDDEN','DELETED')),
 "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP, "updatedAt" TIMESTAMP(3) NOT NULL,
 CHECK ("category" IN ('정보','질문','건의','자유'))
);
CREATE INDEX "BoardPost_status_category_createdAt_idx" ON "BoardPost"("status","category","createdAt");
CREATE INDEX "BoardPost_status_createdAt_idx" ON "BoardPost"("status","createdAt");
CREATE TABLE "BoardComment" (
 "id" TEXT PRIMARY KEY, "postId" TEXT NOT NULL REFERENCES "BoardPost"("id") ON DELETE CASCADE,
 "nickname" VARCHAR(24) NOT NULL, "body" VARCHAR(2000) NOT NULL CHECK (length(trim("body")) > 0),
 "passwordHash" TEXT NOT NULL, "status" TEXT NOT NULL DEFAULT 'PUBLIC' CHECK ("status" IN ('PUBLIC','PENDING','HIDDEN','DELETED')),
 "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP, "updatedAt" TIMESTAMP(3) NOT NULL
);
CREATE INDEX "BoardComment_postId_status_createdAt_idx" ON "BoardComment"("postId","status","createdAt");
CREATE TABLE "BoardReport" (
 "id" TEXT PRIMARY KEY, "postId" TEXT REFERENCES "BoardPost"("id") ON DELETE CASCADE,
 "commentId" TEXT REFERENCES "BoardComment"("id") ON DELETE CASCADE,
 "reason" TEXT NOT NULL CHECK ("reason" IN ('광고·스팸','음란물','혐오·차별','기타')),
 "status" TEXT NOT NULL DEFAULT 'OPEN' CHECK ("status" IN ('OPEN','RESOLVED')),
 "reporter" TEXT, "expiresAt" TIMESTAMP(3) NOT NULL, "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
 CHECK (("postId" IS NULL) <> ("commentId" IS NULL))
);
CREATE INDEX "BoardReport_status_createdAt_idx" ON "BoardReport"("status","createdAt");
CREATE INDEX "BoardReport_reporter_createdAt_idx" ON "BoardReport"("reporter","createdAt");
CREATE TABLE "BoardGuard" ("key" TEXT PRIMARY KEY, "count" INTEGER NOT NULL DEFAULT 1, "expiresAt" TIMESTAMP(3) NOT NULL);
CREATE INDEX "BoardGuard_expiresAt_idx" ON "BoardGuard"("expiresAt");
CREATE TABLE "BoardAudit" (
 "id" TEXT PRIMARY KEY, "adminId" INTEGER NOT NULL, "targetId" TEXT NOT NULL, "targetType" TEXT NOT NULL,
 "action" TEXT NOT NULL, "reason" VARCHAR(500) NOT NULL, "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX "BoardAudit_createdAt_idx" ON "BoardAudit"("createdAt");
