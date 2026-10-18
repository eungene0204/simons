ALTER TABLE "BoardPost" DROP CONSTRAINT "BoardPost_category_check";
ALTER TABLE "BoardPost"
  ADD CONSTRAINT "BoardPost_category_check"
  CHECK ("category" IN ('공지', '정보', '질문', '건의', '자유'));
