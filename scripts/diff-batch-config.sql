-- public.tables 의 batch_time / frequency / batch_day_of_month 가
-- scripts/expected-batch-config.json 의 기대값과 일치하는지 비교.
-- 모든 출력은 KST 기준이며 read-only (UPDATE 미수행).
--
-- 사용 (cloud-sql proxy on 127.0.0.1:5433 가정):
--   op run --env-file=dev.env.tpl -- \
--     psql "postgresql://USER:PASS@127.0.0.1:5433/dfm_bq_load_alerter" \
--     -f scripts/diff-batch-config.sql
-- 또는 어플리케이션 DSN 을 그대로 사용하되 asyncpg → psql 변환만 처리.

\set ON_ERROR_STOP on

-- =========================================================================
-- 1) 업데이트 대상: project_id+dataset+table_name 매치되지만 batch_time /
--    frequency / batch_day_of_month 가 다른 행.
--    DB 의 project_id 가 NULL 이면 settings.bq_project_id 폴백을 받는다는
--    점을 감안하여, NULL 인 행은 expected.project_id 와 매치되는 후보로 본다.
-- =========================================================================
\echo '== 1) UPDATE 필요 (batch_time / frequency / batch_day_of_month 불일치) =='
WITH expected (project_id, dataset, table_name, batch_time, frequency, batch_day_of_month) AS (
    VALUES
        ('emart-datafabric', 'bw', 'ZSD_AD500',       TIME '07:13:06', 'daily',   NULL::int),
        ('emart-datafabric', 'bw', 'ZMM_AD130',       TIME '05:35:49', 'daily',   NULL),
        ('emart-datafabric', 'bw', 'ZMM_AD047',       TIME '05:49:40', 'daily',   NULL),
        ('emart-datafabric', 'bw', 'PZCAMPNID',       TIME '01:45:10', 'daily',   NULL),
        ('emart-datafabric', 'bw', 'PZEVENTID',       TIME '01:45:50', 'daily',   NULL),
        ('emart-datafabric', 'bw', 'PRT_OFFER',       TIME '01:43:58', 'daily',   NULL),
        ('emart-datafabric', 'bw', 'ZSD_MG500_TMP',   TIME '13:39:01', 'daily',   NULL),
        ('emart-datafabric', 'bw', 'ZSD_AD704',       TIME '05:01:51', 'daily',   NULL),
        ('emart-datafabric', 'bw', 'ZSD_AD501',       TIME '07:21:59', 'monthly', 2),
        ('emart-datafabric', 'bw', 'ZHR_AD007',       TIME '07:32:01', 'daily',   NULL),
        ('emart-datafabric', 'bw', 'PMATERIAL',       TIME '01:32:00', 'daily',   NULL),
        ('emart-datafabric', 'bw', 'PVENDOR',         TIME '01:41:08', 'daily',   NULL),
        ('emart-datafabric', 'bw', 'CODE_MATERIAL',   TIME '00:27:59', 'daily',   NULL),
        ('smart-ruler-304409', 'cds_amt', 'TB_AMT_CMMN_CUST_DNA_DATA', TIME '07:59:00', 'monthly', 2),
        ('smart-ruler-304409', 'cds_core', 'TB_DW_RCIPT_DETAIL',             TIME '05:30:00', 'daily', NULL),
        ('smart-ruler-304409', 'cds_core', 'TB_DW_POS_EVENT',                TIME '05:35:00', 'daily', NULL),
        ('smart-ruler-304409', 'cds_core', 'TB_DW_POS_EVENT_PRT_STR_MASTR',  TIME '05:30:00', 'daily', NULL),
        ('smart-ruler-304409', 'cds_core', 'TB_DW_RCIPT_DETAIL_EMT_MALL',    TIME '07:40:00', 'daily', NULL),
        ('smart-ruler-304409', 'cds_core', 'TB_DW_PRDT_MASTR',               TIME '05:30:00', 'daily', NULL),
        ('smart-ruler-304409', 'cds_core', 'TB_DW_PRDT_DI_CD',               TIME '05:30:00', 'daily', NULL),
        ('smart-ruler-304409', 'cds_core', 'TB_DW_PRDT_CAT_CD',              TIME '05:30:00', 'daily', NULL),
        ('smart-ruler-304409', 'cds_core', 'TB_DW_PRDT_GCODE_CD',            TIME '05:30:00', 'daily', NULL),
        ('smart-ruler-304409', 'cds_core', 'TB_DW_PRDT_MCODE_CD',            TIME '05:30:00', 'daily', NULL),
        ('smart-ruler-304409', 'cds_core', 'TB_DW_PRDT_DCODE_CD',            TIME '05:30:00', 'daily', NULL),
        ('smart-ruler-304409', 'cds_core', 'TB_DW_STR_MASTR',                TIME '05:30:00', 'daily', NULL),
        ('smart-ruler-304409', 'cds_core', 'TB_DW_DT_MASTR',                 TIME '05:30:00', 'daily', NULL),
        ('smart-ruler-304409', 'cds_core', 'TB_DW_OMNI_CUST_AGREE',          TIME '05:35:00', 'daily', NULL),
        ('smart-ruler-304409', 'cds_core', 'TB_DW_POS_EVENT_PRDT_MASTR',     TIME '05:30:00', 'daily', NULL),
        ('smart-ruler-304409', 'cds_core', 'TB_DW_CUST_MASTR',               TIME '05:30:00', 'daily', NULL)
)
SELECT
    t.id,
    COALESCE(t.project_id, '(NULL→폴백)') AS db_project_id,
    t.dataset,
    t.table_name,
    t.batch_time              AS db_batch_time,
    e.batch_time              AS expected_batch_time,
    t.frequency::text         AS db_frequency,
    e.frequency               AS expected_frequency,
    t.batch_day_of_month      AS db_dom,
    e.batch_day_of_month      AS expected_dom,
    CASE WHEN t.batch_time         IS DISTINCT FROM e.batch_time         THEN 'Y' ELSE '' END AS d_time,
    CASE WHEN t.frequency::text    IS DISTINCT FROM e.frequency          THEN 'Y' ELSE '' END AS d_freq,
    CASE WHEN t.batch_day_of_month IS DISTINCT FROM e.batch_day_of_month THEN 'Y' ELSE '' END AS d_dom
FROM public.tables t
JOIN expected e
  ON  t.dataset    = e.dataset
  AND t.table_name = e.table_name
  AND (t.project_id = e.project_id OR t.project_id IS NULL)
WHERE
       t.batch_time         IS DISTINCT FROM e.batch_time
    OR t.frequency::text    IS DISTINCT FROM e.frequency
    OR t.batch_day_of_month IS DISTINCT FROM e.batch_day_of_month
ORDER BY t.dataset, t.table_name;

-- =========================================================================
-- 2) JSON 에는 있는데 DB 에는 없는 테이블 (등록 필요 후보).
-- =========================================================================
\echo '== 2) JSON 에는 있으나 DB 에 없음 (등록 필요 후보) =='
WITH expected (project_id, dataset, table_name) AS (
    VALUES
        ('emart-datafabric', 'bw', 'ZSD_AD500'),
        ('emart-datafabric', 'bw', 'ZMM_AD130'),
        ('emart-datafabric', 'bw', 'ZMM_AD047'),
        ('emart-datafabric', 'bw', 'PZCAMPNID'),
        ('emart-datafabric', 'bw', 'PZEVENTID'),
        ('emart-datafabric', 'bw', 'PRT_OFFER'),
        ('emart-datafabric', 'bw', 'ZSD_MG500_TMP'),
        ('emart-datafabric', 'bw', 'ZSD_AD704'),
        ('emart-datafabric', 'bw', 'ZSD_AD501'),
        ('emart-datafabric', 'bw', 'ZHR_AD007'),
        ('emart-datafabric', 'bw', 'PMATERIAL'),
        ('emart-datafabric', 'bw', 'PVENDOR'),
        ('emart-datafabric', 'bw', 'CODE_MATERIAL'),
        ('smart-ruler-304409', 'cds_amt', 'TB_AMT_CMMN_CUST_DNA_DATA'),
        ('smart-ruler-304409', 'cds_core', 'TB_DW_RCIPT_DETAIL'),
        ('smart-ruler-304409', 'cds_core', 'TB_DW_POS_EVENT'),
        ('smart-ruler-304409', 'cds_core', 'TB_DW_POS_EVENT_PRT_STR_MASTR'),
        ('smart-ruler-304409', 'cds_core', 'TB_DW_RCIPT_DETAIL_EMT_MALL'),
        ('smart-ruler-304409', 'cds_core', 'TB_DW_PRDT_MASTR'),
        ('smart-ruler-304409', 'cds_core', 'TB_DW_PRDT_DI_CD'),
        ('smart-ruler-304409', 'cds_core', 'TB_DW_PRDT_CAT_CD'),
        ('smart-ruler-304409', 'cds_core', 'TB_DW_PRDT_GCODE_CD'),
        ('smart-ruler-304409', 'cds_core', 'TB_DW_PRDT_MCODE_CD'),
        ('smart-ruler-304409', 'cds_core', 'TB_DW_PRDT_DCODE_CD'),
        ('smart-ruler-304409', 'cds_core', 'TB_DW_STR_MASTR'),
        ('smart-ruler-304409', 'cds_core', 'TB_DW_DT_MASTR'),
        ('smart-ruler-304409', 'cds_core', 'TB_DW_OMNI_CUST_AGREE'),
        ('smart-ruler-304409', 'cds_core', 'TB_DW_POS_EVENT_PRDT_MASTR'),
        ('smart-ruler-304409', 'cds_core', 'TB_DW_CUST_MASTR')
)
SELECT e.project_id, e.dataset, e.table_name
FROM expected e
LEFT JOIN public.tables t
  ON  t.dataset    = e.dataset
  AND t.table_name = e.table_name
  AND (t.project_id = e.project_id OR t.project_id IS NULL)
WHERE t.id IS NULL
ORDER BY e.project_id, e.dataset, e.table_name;

-- =========================================================================
-- 3) DB 에는 있으나 JSON 에 없음 (등록 해제 / 검토 대상).
--    project_id 가 NULL 인 행은 settings.bq_project_id 폴백을 받는 것으로
--    보고 함께 출력 (실제 매핑은 운영자가 확인).
-- =========================================================================
\echo '== 3) DB 에는 있으나 JSON 에 없음 (project_id.dataset.table_name) =='
WITH expected (project_id, dataset, table_name) AS (
    VALUES
        ('emart-datafabric', 'bw', 'ZSD_AD500'),
        ('emart-datafabric', 'bw', 'ZMM_AD130'),
        ('emart-datafabric', 'bw', 'ZMM_AD047'),
        ('emart-datafabric', 'bw', 'PZCAMPNID'),
        ('emart-datafabric', 'bw', 'PZEVENTID'),
        ('emart-datafabric', 'bw', 'PRT_OFFER'),
        ('emart-datafabric', 'bw', 'ZSD_MG500_TMP'),
        ('emart-datafabric', 'bw', 'ZSD_AD704'),
        ('emart-datafabric', 'bw', 'ZSD_AD501'),
        ('emart-datafabric', 'bw', 'ZHR_AD007'),
        ('emart-datafabric', 'bw', 'PMATERIAL'),
        ('emart-datafabric', 'bw', 'PVENDOR'),
        ('emart-datafabric', 'bw', 'CODE_MATERIAL'),
        ('smart-ruler-304409', 'cds_amt', 'TB_AMT_CMMN_CUST_DNA_DATA'),
        ('smart-ruler-304409', 'cds_core', 'TB_DW_RCIPT_DETAIL'),
        ('smart-ruler-304409', 'cds_core', 'TB_DW_POS_EVENT'),
        ('smart-ruler-304409', 'cds_core', 'TB_DW_POS_EVENT_PRT_STR_MASTR'),
        ('smart-ruler-304409', 'cds_core', 'TB_DW_RCIPT_DETAIL_EMT_MALL'),
        ('smart-ruler-304409', 'cds_core', 'TB_DW_PRDT_MASTR'),
        ('smart-ruler-304409', 'cds_core', 'TB_DW_PRDT_DI_CD'),
        ('smart-ruler-304409', 'cds_core', 'TB_DW_PRDT_CAT_CD'),
        ('smart-ruler-304409', 'cds_core', 'TB_DW_PRDT_GCODE_CD'),
        ('smart-ruler-304409', 'cds_core', 'TB_DW_PRDT_MCODE_CD'),
        ('smart-ruler-304409', 'cds_core', 'TB_DW_PRDT_DCODE_CD'),
        ('smart-ruler-304409', 'cds_core', 'TB_DW_STR_MASTR'),
        ('smart-ruler-304409', 'cds_core', 'TB_DW_DT_MASTR'),
        ('smart-ruler-304409', 'cds_core', 'TB_DW_OMNI_CUST_AGREE'),
        ('smart-ruler-304409', 'cds_core', 'TB_DW_POS_EVENT_PRDT_MASTR'),
        ('smart-ruler-304409', 'cds_core', 'TB_DW_CUST_MASTR')
)
SELECT
    COALESCE(t.project_id, '(NULL→bq_project_id 폴백)') AS project_id,
    t.dataset,
    t.table_name,
    COALESCE(t.project_id, '∅') || '.' || t.dataset || '.' || t.table_name AS fqn
FROM public.tables t
LEFT JOIN expected e
  ON  t.dataset    = e.dataset
  AND t.table_name = e.table_name
  AND (t.project_id = e.project_id OR t.project_id IS NULL)
WHERE e.table_name IS NULL
ORDER BY t.project_id NULLS FIRST, t.dataset, t.table_name;
