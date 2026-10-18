UPDATE "BoardPost" SET "status" = 'PUBLIC' WHERE "status" = 'PENDING';
UPDATE "BoardComment" SET "status" = 'PUBLIC' WHERE "status" = 'PENDING';
ALTER TABLE "BoardPost" DROP CONSTRAINT "BoardPost_status_check";
ALTER TABLE "BoardPost"
  ADD CONSTRAINT "BoardPost_status_check"
  CHECK ("status" IN ('PUBLIC', 'HIDDEN', 'DELETED'));
ALTER TABLE "BoardComment" DROP CONSTRAINT "BoardComment_status_check";
ALTER TABLE "BoardComment"
  ADD CONSTRAINT "BoardComment_status_check"
  CHECK ("status" IN ('PUBLIC', 'HIDDEN', 'DELETED'));
