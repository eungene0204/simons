# 테스트 정리 기록 — KR 규칙 경로 폐지 후 (2026-10-15)

해석 안정화 수리(`6dc23e6e`)를 `main`에 합친 뒤 백엔드 테스트가 503건 실패·프론트 32파일 실패였다. 원인을 가려
고치고, 폐지된 기능의 테스트는 기능과 함께 삭제했다(사용자 지시: "기능을 삭제할 때 관련 유닛테스트도 같이 지운다").

## 결과(로컬, CI와 같은 제외 조건)

- 백엔드: 실패 503 → 0 목표(마지막 전체 실행 결과는 PR/커밋 본문 참고). 프론트: `npm run test:frontend` 전부 통과.
- 삭제한 테스트 함수 225개(아래 목록). 같은 작업에서 코드 결함 7건을 고쳤다.

## 삭제 기준

1. 테스트가 **한국어 원문을 정규식으로 해석하던 경로**(규칙 파서·레거시 분류기·결정적 빌더 이해·롤백 override)를 검사한다.
   그 경로는 KR에서 폐지됐다(CLAUDE.md 첫 단락, `docs/nl_interpretation_contract.md`).
2. 한국어 기본 상태에서 실패하고, 영어 레인으로 바꿔야만 통과했다(=한국어 원문 정규식이 입력).
3. 규칙 파서를 **입력 생성에만** 쓰고 검사 대상이 살아 있는 코드면 삭제하지 않고 입력을 직접 만들어 되살렸다
   (`test_parse_validator`, 단일 종목 변환, ETF 테마 canonical DSL, RSI 빌더 상태 → DSL, step-stream SSE 단계 이벤트).
4. 영어(/us) 레인에만 코드가 남은 기능(후행 검증·검증기)은 영어 레인으로 명시해 되살렸다.

## 고친 결함(코드)

| 위치 | 증상 | 회귀 테스트 |
|---|---|---|
| `engine/nl_parser.py::_detect_qualitative_metrics` | KR 분기가 정의되지 않은 `parsed`를 반환 → 한국어 요청에서 `NameError` | `test_detect_qualitative_metrics_returns_empty_list_outside_the_english_lane` |
| `main.py` primary 수정 결과 | 제외된 재무 조건 안내(`dropped_filter_notices`)가 결과에서 사라져 조용한 드롭 | `test_interpretation_authority::test_unknown_metric_is_dropped_with_a_notice_not_a_500` |
| `response/notice_assembly.py` | 이미 반영된 손절을 "지원하지 않아" 안내(`_covered_by_risk_values` 누락) | `test_strategy_conversation::test_primary_unsupported_report_echoing_reflected_stop_loss_is_not_noticed` |
| `response/notice_assembly.py` | 값 대기 근사 조건의 문장 조각이 "지원하지 않아"로 이중 안내 | `test_primary_approximated_condition_fragment_not_noticed_as_unsupported` |
| `primary.py` 보류 경로 | 되묻기 옵션 칩·구분 문구 소실 | `test_cross_period_clarification`, `test_agent_audit3_fixes`(칩 단정) |
| `intent/strategy_builder.py::_step_semantic` | LLM 장애가 빌더 턴을 예외로 종료 | `test_builder_freetext_interpreter::test_step_llm_failure_keeps_unrecognized_flow` |
| `app/analytics/new/conversationDecision.ts` | 매개변수 `metric`과 지역변수 중복 선언 → 화면 테스트 30여 파일 로딩 불가 | 화면 테스트 전체가 로딩됨 |

## 기대값을 새 설계에 맞춘 테스트

- 보류 고지: 거부된 자유 서술이 `None`이 아니라 `({}, ["…보류했어요"])`(`builder_freetext`).
- 보류 파이프라인이 처리한 수정 턴의 `mode`는 `primary_modify`(`audit3`·`cross_period`·`modify_roundtrip`) — 칩·문구·전략 무변경 단정은 유지.
- 결과에 `strategy_version`이 더해짐(`observability_parse_root`, `trace_fixture`) — 기존 항목 불변 단정으로 교체.
- 보조 판정 호출은 해석기 호출 횟수에서 제외(`strategy_conversation`, `contributions`, `required_verdict_dependencies`).
- 프론트: 분류 응답의 구조화 축(`turn_action`·`research_metric`)을 주입, 스켈레톤이 원문을 읽지 않는 새 동작 반영.

## 후속 필요 — 살아 있는 동작인데 테스트가 줄어든 곳

삭제한 결정적 빌더·분류 테스트 중 일부는 **값 범위 검증·재시작·되돌리기·미인식 누적** 같은 살아 있는 흐름을 한국어 결정적
입력으로 건드렸다. 그 입력 경로가 폐지돼 지웠으나, 같은 흐름을 **해석기 스텁(LLM 연산)** 으로 다시 검증하는 테스트는
아직 없다. 우선순위 후보: ① `miss_streak` 증가·리셋, ② 손절·익절 범위 거부와 파라미터 불변식, ③ 처음부터 다시(restart),
④ 값 없는 수정 요청(칩 재전송) 왕복, ⑤ 빌더 필터 제거·단독 수정.

## 보고(정리 필요 코드)

- `app/api/strategy/parse/stream/route.ts`의 `buildSkeleton`·`inferUniverse`(원문 정규식)는 호출처가 사라진 채 남아 있다.
  CLAUDE.md "현행 격차" 표 갱신과 함께 삭제를 결정할 것.
- `data/korea-stocks.json` 의존 테스트 중 `test_backfill_us_stocks::test_columns_match_korean_schema`는 로컬 parquet 미러가 있어야
  실행되는 데이터 의존 테스트로, 이번 변경과 무관하게 한국 스키마에 컬럼이 늘어 실패한다(CI는 parquet이 없어 건너뜀).

## 삭제한 테스트 함수 목록

### `backend/tests/test_ai_runtime_latency.py` (1)
`test_parse_stream_emits_parsing_stage_and_result`

### `backend/tests/test_builder_freetext_interpreter.py` (2)
`test_freetext_mode_env_gate`, `test_step_deterministic_answer_skips_llm_lane`

### `backend/tests/test_builder_modify_rules.py` (16)
`test_combined_answer_fills_current_field_and_risk`, `test_etf_universe_change_blocked_when_value_strategy_set`, `test_filter_modified_mid_flow_with_explicit_word`, `test_remove_all_filters_generic_word`, `test_remove_and_set_in_one_message`, `test_remove_holding_count_reasks_required_field`, `test_remove_last_risk_condition_reopens_risk_step`, `test_remove_rebalance_becomes_none`, `test_remove_sector_restriction`, `test_remove_specific_filter_keeps_others`, `test_remove_stop_loss_keeps_take_profit`, `test_risk_mentioned_ahead_is_captured_and_not_reasked`, `test_stop_loss_cancel_word_is_removal_not_builder_exit`, `test_valueless_risk_change_keeps_value_and_reopens_step`, `test_valueless_type_change_resets_type_params`, `test_valueless_universe_change_reasks_market`

### `backend/tests/test_builder_single_asset.py` (2)
`test_free_description_becomes_custom_entry`, `test_momentum_and_value_blocked_with_explanation`

### `backend/tests/test_builder_step_stream.py` (4)
`test_step_seed_recognized_false_on_followup_turn`, `test_step_seed_recognized_true_for_concrete_strategy_seed`, `test_step_seed_recognized_true_for_universe_only_seed`, `test_step_stream_seed_recognized_flag`

### `backend/tests/test_condition_builder.py` (1)
`test_clarification_chips_roundtrip_through_modify`

### `backend/tests/test_intent_classifier.py` (37)
`test_anaphora_uses_last_symbol`, `test_classify_normalizes_count_typo_before_llm`, `test_definition_beats_strategy_keyword`, `test_definition_question_is_general`, `test_definition_with_construct_verb_stays_strategy`, `test_followup_with_history_passes_context_to_llm`, `test_fundamental_screening_is_strategy`, `test_greeting_is_detected`, `test_greeting_with_strategy_question_is_strategy`, `test_history_does_not_affect_deterministic_rules`, `test_llm_fallback_offtopic_overridden_when_finance_cue_present`, `test_mixed_news_request_stays_strategy`, `test_named_stock_is_not_pick_redirect`, `test_named_stock_news_question_is_stock_analysis`, `test_no_history_keeps_plain_query_for_llm`, `test_offtopic_is_refused`, `test_onboarding_does_not_steal_strategy_question`, `test_onboarding_help_is_routed_to_builder`, `test_open_stock_pick_is_redirected`, `test_open_strategy_pick_is_routed_to_builder`, `test_overseas_alias_detected_but_marked_overseas`, `test_risk_word_with_other_strategy_evidence_stays_strategy`, `test_screening_basket_recommend_is_strategy`, `test_spec_examples`, `test_specific_strategy_is_not_pick`, `test_stock_name_with_test_cue_is_strategy`, `test_stock_question_extracts_symbol`, `test_stock_question_redirect_first_example_uses_stock_sector`, `test_stock_question_redirect_sector_example_is_parseable`, `test_stock_question_redirects_to_strategy_building`, `test_stock_question_with_risk_word_only_is_stock_analysis`, `test_strategy_keyword_beats_stock_name`, `test_strategy_modification_is_strategy_not_pick`, `test_substring_match_bug_sk_hynix_not_confused_with_inix`, `test_theme_invest_guards_keep_existing_routes`, `test_theme_invest_mention_routes_to_strategy`, `test_unsupported_feature_request_is_declined_not_built`

### `backend/tests/test_nl_parser_overrides.py` (68)
`test_bf19_korean_percent_notation_normalized_in_compact`, `test_consult_guard_falls_back_when_judge_says_so`, `test_etf_supported_universe_rule_parse_and_no_notice`, `test_explicit_no_rebalancing_screen_is_not_forced_monthly`, `test_fundamental_screen_parses_without_llm`, `test_llm_all_null_diff_is_not_reinterpreted_by_postprocessing`, `test_llm_modification_diff_is_authoritative_across_domains`, `test_llm_modification_diff_is_authoritative_for_risk_fields`, `test_llm_modification_preserves_unknown_stop_loss_typo`, `test_missing_entry_clarification_asks_numbers_for_qualitative_metrics`, `test_missing_entry_clarification_still_asks_for_valueless_signal_metric`, `test_modify_bare_capital_amount_updates_summary`, `test_modify_count_typo_updates_max_positions`, `test_modify_dividend_ev_ebitda_filters_resolve_deterministically`, `test_modify_increase_positions_resolves_deterministically`, `test_modify_numeric_sector_resolves_deterministically`, `test_modify_sector_additive_union`, `test_modify_sector_combined_with_risk_field_deterministically`, `test_modify_sector_removal_not_reinjected`, `test_modify_sector_replace_without_additive_cue`, `test_modify_sector_targeted_removal`, `test_modify_stop_loss_number_not_misread_as_capital`, `test_modify_two_year_backtest_with_take_profit_resolves_deterministically`, `test_modify_without_sector_mention_preserves_previous_sector`, `test_modify_year_month_backtest_range_resolves_deterministically`, `test_operating_margin_without_threshold_removes_substitute_and_asks_percentage`, `test_operating_profit_strategy_parses_deterministically`, `test_parse_emits_thinking_stage_before_llm_fallback`, `test_parse_modification_changes_universe_when_prompt_explicitly_requests_it`, `test_parse_modification_complex_request_defers_to_llm`, `test_parse_modification_llm_filter_diff_merges_with_existing`, `test_parse_modification_removes_rebalancing_on_llm_path_when_diff_is_null`, `test_parse_modification_trusts_llm_universe_diff_without_keyword_gate`, `test_parse_raises_on_invalid_llm_output_instead_of_regex_fallback`, `test_parse_routes_to_llm_when_guard_rejects`, `test_parse_rule_based_bimonthly_inspection`, `test_parse_rule_based_path_does_not_emit_thinking_stage`, `test_parse_rule_based_returns_strategy_without_touching_model`, `test_profitable_last_year_strategy_parses_deterministically`, `test_ranking_keeps_explicit_day_holding_period`, `test_ranking_keeps_rebalancing_even_when_negated`, `test_ranking_still_drops_momentum_lookback_as_holding_period`, `test_rule_based_modification_keeps_seed_capital_change`, `test_rule_based_parses_box_breakout_full_prompt`, `test_rule_based_parses_relative_strength_ranking_full_prompt`, `test_rule_based_strategy_multifactor_ema_prompt_catches_entry_signals`, `test_rule_based_strategy_multifactor_prompt_keeps_default_capital`, `test_rule_based_strategy_parses_52_week_high_volume_spike_prompt_without_llm`, `test_rule_based_strategy_parses_explicit_value_hold_prompt_without_llm`, `test_rule_based_strategy_parses_pbr_particle_unit_prompt_without_llm`, `test_rule_based_strategy_parses_price_above_ma_with_volume_prompt_without_llm`, `test_rule_based_strategy_parses_technical_prompt_with_risk_without_llm`, `test_rule_based_strategy_parses_trading_value_particle_prompt_without_llm`, `test_rule_based_strategy_parses_weekly_momentum_ranking_prompt_without_llm`, `test_rule_parse_red_flag_not_triggered_on_valid_strategy`, `test_rule_parse_sector_respects_explicit_market`, `test_rule_parse_sector_strategy_sets_sector_and_market_default`, `test_sector_flows_to_backtest_request_and_canonical_dsl`, `test_strategy_ui_entry_suggestion_replaces_ranking_without_llm`, `test_strategy_ui_setting_suggestions_use_deterministic_modification_path`, `test_supported_prompt_not_flagged_as_unsupported`, `test_typo_correction_preserves_original_description`, `test_unresolved_sector_mention_also_gets_both_markets`, `test_unresolved_sector_triggers_reask_clarification`, `test_unsearched_unresolved_sector_keeps_reask`, `test_value_screen_inspection_cycle_parses_quarterly_rebalancing`, `test_value_screen_with_hold_period_does_not_inject_rebalancing`, `test_value_screen_with_take_profit_does_not_inject_rebalancing`

### `backend/tests/test_parse_fallback_blocked.py` (1)
`test_primary_off_keeps_rule_hybrid_as_primary`

### `backend/tests/test_platform_defaults.py` (1)
`test_classify_routes_to_general_with_reply`

### `backend/tests/test_redteam_validation_fixes.py` (8)
`test_fundamental_top_n_is_not_return_ranking`, `test_indicator_typo_is_strategy_not_stock`, `test_live_trading_is_unsupported`, `test_misconception_routes_to_knowledge_answer`, `test_personal_advice_is_not_general_llm_answer`, `test_signal_removal_preserves_other_fields`, `test_strategy_pick_superlative_still_detected`, `test_vague_money_desire_routes_to_onboarding`

### `backend/tests/test_single_asset_backtest.py` (7)
`test_modify_explicit_universe_clears_target`, `test_modify_fast_path_alias_replaces_target`, `test_modify_fast_path_removes_single_target_from_list`, `test_modify_fast_path_replacement_still_works_after_removal_branch`, `test_modify_fast_path_replaces_target`, `test_modify_unrelated_field_preserves_target`, `test_rule_parse_single_asset_entry_only_stays_on_fast_path`

### `backend/tests/test_stock_recognition_regressions.py` (1)
`test_intent_classification`

### `backend/tests/test_strategy_builder.py` (71)
`test_apply_parsed_seed_does_not_override_deterministic_seed`, `test_bf01_proceed_words_not_cancelled`, `test_bf03_definition_question_does_not_fill_strategy_type`, `test_bf04_uncovered_term_gets_fallback_not_silent_repeat`, `test_bf05_change_cue_overwrites_filled_fields`, `test_bf06_correction_takes_value_after_malgo`, `test_bf07_value_direction_conflict_explained_not_flipped`, `test_bf08_risk_out_of_range_rejected_at_input`, `test_bf09_param_invariants_reask_with_hint`, `test_bf10_filter_step_does_not_swallow_unrelated_input`, `test_bf11_single_stock_request_mid_build_gets_guidance`, `test_bf12_etf_value_choice_explained`, `test_bf14_compound_answer_fills_following_slots`, `test_bf15_miss_streak_escalates_and_resets`, `test_bf17_zero_and_over_limit_counts_reask`, `test_bf18_restart_seeds_from_same_message`, `test_bollinger_named_strategy_locks_on_and_skips_generic_menu`, `test_builder_listing_period_chip_answer_is_deterministic`, `test_case1_kospi_after_entry_no_refusal_and_next_question`, `test_case2_bare_kospi_interpreted_as_universe`, `test_case3_three_months_with_momentum`, `test_case4_cancel_resets_to_normal`, `test_compound_theme_not_confirmed_as_head_sector`, `test_custom_entry_rule_captures_explicit_holding_count`, `test_custom_flow_captures_entry_rule`, `test_describe_own_chip_routes_to_free_text_entry_rule`, `test_exit_other_question_returns_to_normal`, `test_filter_none_completes_without_filters`, `test_full_momentum_flow_to_confirmation`, `test_glossary_does_not_intercept_normal_answers`, `test_glossary_question_mid_builder_answers_and_reasks`, `test_holding_count_step_free_text_parses_custom_value`, `test_known_follower_keeps_cue_less_sector`, `test_ma_flow_ema_periods_flow_to_dsl`, `test_midflow_supported_sector_mention_is_captured`, `test_midflow_unresolved_mention_resolved_by_llm`, `test_named_strategy_locks_on_and_asks_own_param`, `test_rebalance_none_option_offered_and_completes`, `test_restart_keeps_builder_and_clears_state`, `test_risk_step_cancel_still_exits`, `test_risk_step_free_text_after_direct_input_parses_custom_value`, `test_risk_step_keyword_first_order_no_misattribution`, `test_risk_step_llm_failure_falls_back_to_regex`, `test_risk_step_llm_recovers_value_regex_missed`, `test_risk_step_negated_stop_loss_not_extracted`, `test_risk_step_parses_stop_loss_with_korean_particle`, `test_risk_step_parses_stop_take_trailing_hold`, `test_risk_step_refusal_explains_why_required`, `test_risk_step_regex_match_skips_llm`, `test_risk_step_regex_takes_priority_over_llm`, `test_risk_step_requires_a_condition_and_reasks_otherwise`, `test_sector_flows_into_prompt_and_dsl`, `test_sector_reask_answered_with_supported_sector`, `test_sector_reask_second_failure_degrades_with_notice`, `test_seed_ai_theme_confirms_catalog_symbols_not_broad_sector`, `test_seed_collects_multiple_sectors`, `test_seed_confirmed_with_unresolved_sector_reasks_then_confirms`, `test_seed_state_asks_only_missing_universe_then_rebalance`, `test_seed_state_prefills_recognized_fields`, `test_seed_state_remembers_sector_and_leading_stock_phrasing`, `test_seed_state_sector_with_jungshim_cue_no_type_lock`, `test_seed_unsupported_sector_caught_not_silently_dropped`, `test_seed_unsupported_sector_word_order_variants`, `test_theme_auto_confirm_after_grounding_resolution`, `test_theme_companies_auto_confirmed_as_symbol_universe`, `test_trend_filter_flow_end_to_end`, `test_typo_sector_corrected_by_llm_resolver`, `test_unresolved_sector_llm_null_or_error_reasks`, `test_unresolved_sector_resolved_by_llm_resolver`, `test_unresolved_sector_resolver_output_is_renormalized`, `test_weak_theme_candidate_seeds_weak_hint`

### `backend/tests/test_strategy_conversation.py` (3)
`test_primary_entry_restored_by_override_when_rolled_back`, `test_primary_mode_gated_by_env`, `test_primary_parse_explicit_dates_override_when_rolled_back`

### `backend/tests/test_template_qa_regressions.py` (2)
`TestParseDeterminism::test_fully_specified_prompt_handled_by_rules`, `TestParseDeterminism::test_rule_based_parse_is_deterministic`
