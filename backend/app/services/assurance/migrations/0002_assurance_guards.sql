-- Assurance integration guards. No shared table or column changes.

CREATE INDEX ix_reviews_case_created ON reviews(case_id, created_at, id);
CREATE INDEX ix_audit_case_occurred ON audit_events(case_id, occurred_at, id);

CREATE TRIGGER documents_integer_counts_insert BEFORE INSERT ON documents
WHEN typeof(NEW.page_count) != 'integer' OR typeof(NEW.size_bytes) != 'integer'
BEGIN SELECT RAISE(ABORT, 'documents_integer_counts'); END;

CREATE TRIGGER documents_integer_counts_update BEFORE UPDATE ON documents
WHEN typeof(NEW.page_count) != 'integer' OR typeof(NEW.size_bytes) != 'integer'
BEGIN SELECT RAISE(ABORT, 'documents_integer_counts'); END;

CREATE TRIGGER cases_integer_quantity_insert BEFORE INSERT ON cases
WHEN typeof(NEW.quantity) != 'integer'
BEGIN SELECT RAISE(ABORT, 'cases_integer_quantity'); END;

CREATE TRIGGER cases_integer_quantity_update BEFORE UPDATE ON cases
WHEN typeof(NEW.quantity) != 'integer'
BEGIN SELECT RAISE(ABORT, 'cases_integer_quantity'); END;

CREATE TRIGGER cases_integer_version_insert BEFORE INSERT ON cases
WHEN typeof(NEW.version) != 'integer' OR NEW.version < 1
BEGIN SELECT RAISE(ABORT, 'cases_integer_version'); END;

CREATE TRIGGER cases_integer_version_update BEFORE UPDATE ON cases
WHEN typeof(NEW.version) != 'integer' OR NEW.version < 1
BEGIN SELECT RAISE(ABORT, 'cases_integer_version'); END;

CREATE TRIGGER documents_integer_version_insert BEFORE INSERT ON documents
WHEN typeof(NEW.version) != 'integer' OR NEW.version < 1
BEGIN SELECT RAISE(ABORT, 'documents_integer_version'); END;

CREATE TRIGGER documents_integer_version_update BEFORE UPDATE ON documents
WHEN typeof(NEW.version) != 'integer' OR NEW.version < 1
BEGIN SELECT RAISE(ABORT, 'documents_integer_version'); END;

CREATE TRIGGER findings_integer_version_insert BEFORE INSERT ON findings
WHEN typeof(NEW.version) != 'integer' OR NEW.version < 1
BEGIN SELECT RAISE(ABORT, 'findings_integer_version'); END;

CREATE TRIGGER findings_integer_version_update BEFORE UPDATE ON findings
WHEN typeof(NEW.version) != 'integer' OR NEW.version < 1
BEGIN SELECT RAISE(ABORT, 'findings_integer_version'); END;

CREATE TRIGGER challenges_integer_version_insert BEFORE INSERT ON challenges
WHEN typeof(NEW.version) != 'integer' OR NEW.version < 1
BEGIN SELECT RAISE(ABORT, 'challenges_integer_version'); END;

CREATE TRIGGER challenges_integer_version_update BEFORE UPDATE ON challenges
WHEN typeof(NEW.version) != 'integer' OR NEW.version < 1
BEGIN SELECT RAISE(ABORT, 'challenges_integer_version'); END;

CREATE TRIGGER repair_proposals_integer_version_insert BEFORE INSERT ON repair_proposals
WHEN typeof(NEW.version) != 'integer' OR NEW.version < 1
BEGIN SELECT RAISE(ABORT, 'repair_proposals_integer_version'); END;

CREATE TRIGGER repair_proposals_integer_version_update BEFORE UPDATE ON repair_proposals
WHEN typeof(NEW.version) != 'integer' OR NEW.version < 1
BEGIN SELECT RAISE(ABORT, 'repair_proposals_integer_version'); END;

CREATE TRIGGER audit_integer_version_insert BEFORE INSERT ON audit_events
WHEN typeof(NEW.resource_version) != 'integer' OR NEW.resource_version < 1
BEGIN SELECT RAISE(ABORT, 'audit_integer_version'); END;

CREATE TRIGGER meaningful_review_reason_insert BEFORE INSERT ON reviews
WHEN length(trim(NEW.decision_reason)) < 10 OR length(trim(NEW.decision_reason)) > 4000
BEGIN SELECT RAISE(ABORT, 'meaningful_review_reason'); END;

CREATE TRIGGER idempotency_scope_insert BEFORE INSERT ON idempotency_records
WHEN length(trim(NEW.key)) = 0 OR length(NEW.key) > 200 OR NEW.method != upper(NEW.method) OR substr(NEW.route,1,8) != '/api/v1/' OR length(NEW.request_hash) != 64 OR NEW.request_hash GLOB '*[^0-9a-f]*' OR typeof(NEW.response_status) != 'integer' OR NEW.response_status < 200 OR NEW.response_status > 299
BEGIN SELECT RAISE(ABORT, 'idempotency_scope'); END;

CREATE TRIGGER idempotency_scope_update BEFORE UPDATE ON idempotency_records
WHEN length(trim(NEW.key)) = 0 OR length(NEW.key) > 200 OR NEW.method != upper(NEW.method) OR substr(NEW.route,1,8) != '/api/v1/' OR length(NEW.request_hash) != 64 OR NEW.request_hash GLOB '*[^0-9a-f]*' OR typeof(NEW.response_status) != 'integer' OR NEW.response_status < 200 OR NEW.response_status > 299
BEGIN SELECT RAISE(ABORT, 'idempotency_scope'); END;

CREATE TRIGGER documents_live_case_insert BEFORE INSERT ON documents
WHEN NOT EXISTS (SELECT 1 FROM cases WHERE id=NEW.case_id AND deleted_at IS NULL)
BEGIN SELECT RAISE(ABORT, 'documents_live_case'); END;

CREATE TRIGGER analysis_jobs_live_case_insert BEFORE INSERT ON analysis_jobs
WHEN NOT EXISTS (SELECT 1 FROM cases WHERE id=NEW.case_id AND deleted_at IS NULL)
BEGIN SELECT RAISE(ABORT, 'analysis_jobs_live_case'); END;

CREATE TRIGGER ai_executions_live_case_insert BEFORE INSERT ON ai_executions
WHEN NOT EXISTS (SELECT 1 FROM cases WHERE id=NEW.case_id AND deleted_at IS NULL)
BEGIN SELECT RAISE(ABORT, 'ai_executions_live_case'); END;

CREATE TRIGGER findings_live_case_insert BEFORE INSERT ON findings
WHEN NOT EXISTS (SELECT 1 FROM cases WHERE id=NEW.case_id AND deleted_at IS NULL)
BEGIN SELECT RAISE(ABORT, 'findings_live_case'); END;

CREATE TRIGGER challenges_live_case_insert BEFORE INSERT ON challenges
WHEN NOT EXISTS (SELECT 1 FROM cases WHERE id=NEW.case_id AND deleted_at IS NULL)
BEGIN SELECT RAISE(ABORT, 'challenges_live_case'); END;

CREATE TRIGGER simulations_live_case_insert BEFORE INSERT ON simulations
WHEN NOT EXISTS (SELECT 1 FROM cases WHERE id=NEW.case_id AND deleted_at IS NULL)
BEGIN SELECT RAISE(ABORT, 'simulations_live_case'); END;

CREATE TRIGGER repair_proposals_live_case_insert BEFORE INSERT ON repair_proposals
WHEN NOT EXISTS (SELECT 1 FROM cases WHERE id=NEW.case_id AND deleted_at IS NULL)
BEGIN SELECT RAISE(ABORT, 'repair_proposals_live_case'); END;

CREATE TRIGGER reviews_live_case_insert BEFORE INSERT ON reviews
WHEN NOT EXISTS (SELECT 1 FROM cases WHERE id=NEW.case_id AND deleted_at IS NULL)
BEGIN SELECT RAISE(ABORT, 'reviews_live_case'); END;

CREATE TRIGGER document_pages_live_page_insert BEFORE INSERT ON document_pages
WHEN typeof(NEW.page_number) != 'integer' OR NEW.page_number < 1 OR NOT EXISTS (SELECT 1 FROM documents WHERE id=NEW.document_id AND deleted_at IS NULL AND NEW.page_number <= page_count)
BEGIN SELECT RAISE(ABORT, 'document_pages_live_page'); END;

CREATE TRIGGER document_pages_live_page_update BEFORE UPDATE ON document_pages
WHEN typeof(NEW.page_number) != 'integer' OR NEW.page_number < 1 OR NOT EXISTS (SELECT 1 FROM documents WHERE id=NEW.document_id AND deleted_at IS NULL AND NEW.page_number <= page_count)
BEGIN SELECT RAISE(ABORT, 'document_pages_live_page'); END;

CREATE TRIGGER evidence_refs_live_page_insert BEFORE INSERT ON evidence_refs
WHEN typeof(NEW.page_number) != 'integer' OR NEW.page_number < 1 OR NOT EXISTS (SELECT 1 FROM documents WHERE id=NEW.document_id AND deleted_at IS NULL AND NEW.page_number <= page_count)
BEGIN SELECT RAISE(ABORT, 'evidence_refs_live_page'); END;

CREATE TRIGGER evidence_refs_live_page_update BEFORE UPDATE ON evidence_refs
WHEN typeof(NEW.page_number) != 'integer' OR NEW.page_number < 1 OR NOT EXISTS (SELECT 1 FROM documents WHERE id=NEW.document_id AND deleted_at IS NULL AND NEW.page_number <= page_count)
BEGIN SELECT RAISE(ABORT, 'evidence_refs_live_page'); END;

CREATE TRIGGER evidence_same_case_insert BEFORE INSERT ON evidence_refs
WHEN NOT EXISTS (SELECT 1 FROM documents d JOIN findings f ON f.case_id=d.case_id WHERE d.id=NEW.document_id AND f.id=NEW.finding_id)
BEGIN SELECT RAISE(ABORT, 'evidence_same_case'); END;

CREATE TRIGGER evidence_same_case_update BEFORE UPDATE ON evidence_refs
WHEN NOT EXISTS (SELECT 1 FROM documents d JOIN findings f ON f.case_id=d.case_id WHERE d.id=NEW.document_id AND f.id=NEW.finding_id)
BEGIN SELECT RAISE(ABORT, 'evidence_same_case'); END;

CREATE TRIGGER findings_provenance_insert BEFORE INSERT ON findings
WHEN NOT EXISTS (SELECT 1 FROM analysis_jobs j JOIN ai_executions e ON e.case_id=j.case_id WHERE j.id=NEW.analysis_job_id AND e.id=NEW.ai_execution_id AND j.case_id=NEW.case_id)
BEGIN SELECT RAISE(ABORT, 'findings_provenance'); END;

CREATE TRIGGER findings_provenance_update BEFORE UPDATE ON findings
WHEN NOT EXISTS (SELECT 1 FROM analysis_jobs j JOIN ai_executions e ON e.case_id=j.case_id WHERE j.id=NEW.analysis_job_id AND e.id=NEW.ai_execution_id AND j.case_id=NEW.case_id)
BEGIN SELECT RAISE(ABORT, 'findings_provenance'); END;

CREATE TRIGGER retry_same_case_insert BEFORE INSERT ON analysis_jobs
WHEN NEW.retry_of_job_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM analysis_jobs WHERE id=NEW.retry_of_job_id AND case_id=NEW.case_id)
BEGIN SELECT RAISE(ABORT, 'retry_same_case'); END;

CREATE TRIGGER retry_same_case_update BEFORE UPDATE ON analysis_jobs
WHEN NEW.retry_of_job_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM analysis_jobs WHERE id=NEW.retry_of_job_id AND case_id=NEW.case_id)
BEGIN SELECT RAISE(ABORT, 'retry_same_case'); END;

CREATE TRIGGER execution_job_same_case_insert BEFORE INSERT ON ai_executions
WHEN NEW.job_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM analysis_jobs WHERE id=NEW.job_id AND case_id=NEW.case_id)
BEGIN SELECT RAISE(ABORT, 'execution_job_same_case'); END;

CREATE TRIGGER execution_document_same_case_insert BEFORE INSERT ON ai_executions
WHEN json_type(NEW.input_document_ids_json) != 'array' OR EXISTS (SELECT 1 FROM json_each(NEW.input_document_ids_json) entry WHERE NOT EXISTS (SELECT 1 FROM documents WHERE replace(id,'-','')=replace(entry.value,'-','') AND case_id=NEW.case_id AND deleted_at IS NULL))
BEGIN SELECT RAISE(ABORT, 'execution_document_same_case'); END;

CREATE TRIGGER challenges_finding_case_insert BEFORE INSERT ON challenges
WHEN NOT EXISTS (SELECT 1 FROM findings WHERE id=NEW.finding_id AND case_id=NEW.case_id)
BEGIN SELECT RAISE(ABORT, 'challenges_finding_case'); END;

CREATE TRIGGER challenges_finding_case_update BEFORE UPDATE ON challenges
WHEN NOT EXISTS (SELECT 1 FROM findings WHERE id=NEW.finding_id AND case_id=NEW.case_id)
BEGIN SELECT RAISE(ABORT, 'challenges_finding_case'); END;

CREATE TRIGGER simulations_finding_case_insert BEFORE INSERT ON simulations
WHEN NOT EXISTS (SELECT 1 FROM findings WHERE id=NEW.finding_id AND case_id=NEW.case_id)
BEGIN SELECT RAISE(ABORT, 'simulations_finding_case'); END;

CREATE TRIGGER repair_proposals_finding_case_insert BEFORE INSERT ON repair_proposals
WHEN NOT EXISTS (SELECT 1 FROM findings WHERE id=NEW.finding_id AND case_id=NEW.case_id)
BEGIN SELECT RAISE(ABORT, 'repair_proposals_finding_case'); END;

CREATE TRIGGER repair_proposals_finding_case_update BEFORE UPDATE ON repair_proposals
WHEN NOT EXISTS (SELECT 1 FROM findings WHERE id=NEW.finding_id AND case_id=NEW.case_id)
BEGIN SELECT RAISE(ABORT, 'repair_proposals_finding_case'); END;

CREATE TRIGGER challenges_execution_case_insert BEFORE INSERT ON challenges
WHEN NEW.ai_execution_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM ai_executions WHERE id=NEW.ai_execution_id AND case_id=NEW.case_id)
BEGIN SELECT RAISE(ABORT, 'challenges_execution_case'); END;

CREATE TRIGGER challenges_execution_case_update BEFORE UPDATE ON challenges
WHEN NEW.ai_execution_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM ai_executions WHERE id=NEW.ai_execution_id AND case_id=NEW.case_id)
BEGIN SELECT RAISE(ABORT, 'challenges_execution_case'); END;

CREATE TRIGGER repair_proposals_execution_case_insert BEFORE INSERT ON repair_proposals
WHEN NEW.ai_execution_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM ai_executions WHERE id=NEW.ai_execution_id AND case_id=NEW.case_id)
BEGIN SELECT RAISE(ABORT, 'repair_proposals_execution_case'); END;

CREATE TRIGGER repair_proposals_execution_case_update BEFORE UPDATE ON repair_proposals
WHEN NEW.ai_execution_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM ai_executions WHERE id=NEW.ai_execution_id AND case_id=NEW.case_id)
BEGIN SELECT RAISE(ABORT, 'repair_proposals_execution_case'); END;

CREATE TRIGGER repair_simulation_case_insert BEFORE INSERT ON repair_proposals
WHEN NEW.simulation_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM simulations WHERE id=NEW.simulation_id AND finding_id=NEW.finding_id AND case_id=NEW.case_id)
BEGIN SELECT RAISE(ABORT, 'repair_simulation_case'); END;

CREATE TRIGGER repair_simulation_case_update BEFORE UPDATE ON repair_proposals
WHEN NEW.simulation_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM simulations WHERE id=NEW.simulation_id AND finding_id=NEW.finding_id AND case_id=NEW.case_id)
BEGIN SELECT RAISE(ABORT, 'repair_simulation_case'); END;

CREATE TRIGGER review_repair_case_insert BEFORE INSERT ON reviews
WHEN NOT EXISTS (SELECT 1 FROM repair_proposals WHERE id=NEW.repair_proposal_id AND case_id=NEW.case_id AND deleted_at IS NULL AND status='SUBMITTED')
BEGIN SELECT RAISE(ABORT, 'review_repair_case'); END;

CREATE TRIGGER submitted_repair_frozen_update BEFORE UPDATE ON repair_proposals
WHEN OLD.status != 'DRAFT'
BEGIN SELECT RAISE(ABORT, 'submitted_repair_frozen'); END;

CREATE TRIGGER submitted_repair_frozen_delete BEFORE DELETE ON repair_proposals
WHEN OLD.status != 'DRAFT'
BEGIN SELECT RAISE(ABORT, 'submitted_repair_frozen'); END;

CREATE TRIGGER reviewed_case_delete_update BEFORE UPDATE ON cases
WHEN OLD.deleted_at IS NULL AND NEW.deleted_at IS NOT NULL AND EXISTS (SELECT 1 FROM reviews WHERE case_id=OLD.id)
BEGIN SELECT RAISE(ABORT, 'reviewed_case_delete'); END;

CREATE TRIGGER reviewed_document_delete_update BEFORE UPDATE ON documents
WHEN OLD.deleted_at IS NULL AND NEW.deleted_at IS NOT NULL AND EXISTS (SELECT 1 FROM evidence_refs e JOIN repair_proposals p ON p.finding_id=e.finding_id JOIN reviews r ON r.repair_proposal_id=p.id WHERE e.document_id=OLD.id)
BEGIN SELECT RAISE(ABORT, 'reviewed_document_delete'); END;

CREATE TRIGGER page_count_preserves_refs_update BEFORE UPDATE ON documents
WHEN NEW.page_count < OLD.page_count AND (EXISTS (SELECT 1 FROM document_pages WHERE document_id=OLD.id AND page_number>NEW.page_count) OR EXISTS (SELECT 1 FROM evidence_refs WHERE document_id=OLD.id AND page_number>NEW.page_count))
BEGIN SELECT RAISE(ABORT, 'page_count_preserves_refs'); END;
