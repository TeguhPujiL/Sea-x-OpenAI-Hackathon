-- Frozen SQLite baseline: origin/main 45b0c9e. No runtime create_all.

CREATE TABLE cases (
	case_number VARCHAR NOT NULL, 
	title TEXT NOT NULL, 
	category VARCHAR NOT NULL, 
	description TEXT, 
	quantity INTEGER NOT NULL, 
	budget_ceiling_idr INTEGER NOT NULL, 
	currency VARCHAR NOT NULL, 
	case_status VARCHAR(16) NOT NULL, 
	assurance_status VARCHAR(16) NOT NULL, 
	id CHAR(32) NOT NULL, 
	version INTEGER NOT NULL, 
	updated_at DATETIME NOT NULL, 
	created_at DATETIME NOT NULL, 
	deleted_at DATETIME, 
	CONSTRAINT pk_cases PRIMARY KEY (id), 
	CONSTRAINT ck_cases_positive_quantity CHECK (quantity > 0), 
	CONSTRAINT ck_cases_integer_budget CHECK (budget_ceiling_idr >= 0 AND typeof(budget_ceiling_idr) = 'integer'), 
	CONSTRAINT ck_cases_positive_version CHECK (version >= 1), 
	CONSTRAINT ck_cases_idr_currency CHECK (currency = 'IDR'), 
	CONSTRAINT uq_cases_case_number UNIQUE (case_number), 
	CONSTRAINT ck_cases_casestatus CHECK (case_status IN ('DRAFT', 'UNDER_ASSESSMENT', 'UNDER_REVIEW', 'REVIEW_COMPLETED', 'ARCHIVED')), 
	CONSTRAINT ck_cases_assurancestatus CHECK (assurance_status IN ('ACTION_REQUIRED', 'READY_FOR_REVIEW', 'REVIEW_COMPLETED'))
);

CREATE TABLE idempotency_records (
	actor_id CHAR(32) NOT NULL, 
	method VARCHAR NOT NULL, 
	route VARCHAR NOT NULL, 
	"key" VARCHAR NOT NULL, 
	request_hash VARCHAR(64) NOT NULL, 
	response_status INTEGER NOT NULL, 
	response_body JSON NOT NULL, 
	id CHAR(32) NOT NULL, 
	created_at DATETIME NOT NULL, 
	CONSTRAINT pk_idempotency_records PRIMARY KEY (id), 
	CONSTRAINT uq_idempotency_records_actor_id UNIQUE (actor_id, method, route, "key")
);

CREATE TABLE supplier_fixtures (
	data_version VARCHAR NOT NULL, 
	supplier_ref VARCHAR NOT NULL, 
	ram_gb INTEGER NOT NULL, 
	unit_price_idr INTEGER NOT NULL, 
	CONSTRAINT pk_supplier_fixtures PRIMARY KEY (data_version, supplier_ref), 
	CONSTRAINT ck_supplier_fixtures_positive_ram CHECK (ram_gb > 0), 
	CONSTRAINT ck_supplier_fixtures_integer_price CHECK (unit_price_idr >= 0 AND typeof(unit_price_idr) = 'integer')
);

CREATE TABLE analysis_jobs (
	case_id CHAR(32) NOT NULL, 
	analysis_types JSON NOT NULL, 
	processing_status VARCHAR(12) NOT NULL, 
	progress_percent INTEGER NOT NULL, 
	result_json JSON, 
	warnings_json JSON NOT NULL, 
	error_json JSON, 
	retry_of_job_id CHAR(32), 
	started_at DATETIME, 
	completed_at DATETIME, 
	id CHAR(32) NOT NULL, 
	created_at DATETIME NOT NULL, 
	CONSTRAINT pk_analysis_jobs PRIMARY KEY (id), 
	CONSTRAINT ck_analysis_jobs_valid_progress CHECK (progress_percent BETWEEN 0 AND 100), 
	CONSTRAINT fk_analysis_jobs_case_id_cases FOREIGN KEY(case_id) REFERENCES cases (id), 
	CONSTRAINT ck_analysis_jobs_processingstatus CHECK (processing_status IN ('QUEUED', 'PROCESSING', 'COMPLETED', 'FAILED', 'NEEDS_REVIEW')), 
	CONSTRAINT fk_analysis_jobs_retry_of_job_id_analysis_jobs FOREIGN KEY(retry_of_job_id) REFERENCES analysis_jobs (id)
);

CREATE INDEX ix_analysis_jobs_case_id ON analysis_jobs (case_id);

CREATE TABLE audit_events (
	case_id CHAR(32) NOT NULL, 
	actor_id CHAR(32) NOT NULL, 
	request_id VARCHAR NOT NULL, 
	event_type VARCHAR NOT NULL, 
	resource_type VARCHAR NOT NULL, 
	resource_id CHAR(32) NOT NULL, 
	resource_version INTEGER NOT NULL, 
	details_json JSON NOT NULL, 
	occurred_at DATETIME NOT NULL, 
	previous_hash VARCHAR, 
	event_hash VARCHAR, 
	id CHAR(32) NOT NULL, 
	CONSTRAINT pk_audit_events PRIMARY KEY (id), 
	CONSTRAINT ck_audit_events_positive_version CHECK (resource_version >= 1), 
	CONSTRAINT fk_audit_events_case_id_cases FOREIGN KEY(case_id) REFERENCES cases (id)
);

CREATE TABLE documents (
	case_id CHAR(32) NOT NULL, 
	document_type VARCHAR(23) NOT NULL, 
	filename TEXT NOT NULL, 
	description TEXT, 
	storage_key VARCHAR NOT NULL, 
	sha256 VARCHAR(64) NOT NULL, 
	mime_type VARCHAR NOT NULL, 
	size_bytes INTEGER NOT NULL, 
	page_count INTEGER NOT NULL, 
	processing_status VARCHAR(12) NOT NULL, 
	uploaded_at DATETIME NOT NULL, 
	id CHAR(32) NOT NULL, 
	version INTEGER NOT NULL, 
	updated_at DATETIME NOT NULL, 
	created_at DATETIME NOT NULL, 
	deleted_at DATETIME, 
	CONSTRAINT pk_documents PRIMARY KEY (id), 
	CONSTRAINT ck_documents_positive_pages CHECK (page_count >= 1), 
	CONSTRAINT ck_documents_positive_bytes CHECK (size_bytes > 0), 
	CONSTRAINT ck_documents_positive_version CHECK (version >= 1), 
	CONSTRAINT fk_documents_case_id_cases FOREIGN KEY(case_id) REFERENCES cases (id), 
	CONSTRAINT ck_documents_documenttype CHECK (document_type IN ('TOR', 'TECHNICAL_SPECIFICATION', 'OWNER_COST_ESTIMATE', 'TECHNICAL_JUSTIFICATION', 'SUPPLIER_QUOTATION', 'WARRANTY_EVIDENCE', 'EVALUATION_REPORT', 'CONTRACT', 'OTHER')), 
	CONSTRAINT uq_documents_storage_key UNIQUE (storage_key), 
	CONSTRAINT ck_documents_processingstatus CHECK (processing_status IN ('QUEUED', 'PROCESSING', 'COMPLETED', 'FAILED', 'NEEDS_REVIEW'))
);

CREATE INDEX ix_documents_case_id ON documents (case_id);

CREATE TABLE ai_executions (
	job_id CHAR(32), 
	case_id CHAR(32) NOT NULL, 
	provider VARCHAR NOT NULL, 
	model VARCHAR NOT NULL, 
	operation VARCHAR NOT NULL, 
	prompt_version VARCHAR NOT NULL, 
	input_document_ids_json JSON NOT NULL, 
	schema_valid BOOLEAN NOT NULL, 
	evidence_validation_passed BOOLEAN NOT NULL, 
	evidence_checks_json JSON NOT NULL, 
	warnings_json JSON NOT NULL, 
	latency_ms INTEGER NOT NULL, 
	usage_json JSON, 
	id CHAR(32) NOT NULL, 
	created_at DATETIME NOT NULL, 
	CONSTRAINT pk_ai_executions PRIMARY KEY (id), 
	CONSTRAINT ck_ai_executions_nonnegative_latency CHECK (latency_ms >= 0), 
	CONSTRAINT fk_ai_executions_job_id_analysis_jobs FOREIGN KEY(job_id) REFERENCES analysis_jobs (id), 
	CONSTRAINT fk_ai_executions_case_id_cases FOREIGN KEY(case_id) REFERENCES cases (id)
);

CREATE TABLE document_pages (
	document_id CHAR(32) NOT NULL, 
	page_number INTEGER NOT NULL, 
	normalized_text TEXT NOT NULL, 
	id CHAR(32) NOT NULL, 
	CONSTRAINT pk_document_pages PRIMARY KEY (id), 
	CONSTRAINT uq_document_pages_document_id UNIQUE (document_id, page_number), 
	CONSTRAINT ck_document_pages_one_based_page CHECK (page_number >= 1), 
	CONSTRAINT fk_document_pages_document_id_documents FOREIGN KEY(document_id) REFERENCES documents (id)
);

CREATE INDEX ix_document_pages_document_id ON document_pages (document_id);

CREATE TABLE findings (
	case_id CHAR(32) NOT NULL, 
	analysis_job_id CHAR(32) NOT NULL, 
	ai_execution_id CHAR(32) NOT NULL, 
	type VARCHAR NOT NULL, 
	severity VARCHAR(8) NOT NULL, 
	status VARCHAR(12) NOT NULL, 
	title TEXT NOT NULL, 
	summary TEXT NOT NULL, 
	confidence FLOAT NOT NULL, 
	evidence_status VARCHAR(12) NOT NULL, 
	assignee_id CHAR(32), 
	resolution_note TEXT, 
	id CHAR(32) NOT NULL, 
	version INTEGER NOT NULL, 
	updated_at DATETIME NOT NULL, 
	created_at DATETIME NOT NULL, 
	CONSTRAINT pk_findings PRIMARY KEY (id), 
	CONSTRAINT ck_findings_confidence_range CHECK (confidence BETWEEN 0 AND 1), 
	CONSTRAINT ck_findings_positive_version CHECK (version >= 1), 
	CONSTRAINT fk_findings_case_id_cases FOREIGN KEY(case_id) REFERENCES cases (id), 
	CONSTRAINT fk_findings_analysis_job_id_analysis_jobs FOREIGN KEY(analysis_job_id) REFERENCES analysis_jobs (id), 
	CONSTRAINT fk_findings_ai_execution_id_ai_executions FOREIGN KEY(ai_execution_id) REFERENCES ai_executions (id), 
	CONSTRAINT ck_findings_findingseverity CHECK (severity IN ('LOW', 'MEDIUM', 'HIGH', 'CRITICAL')), 
	CONSTRAINT ck_findings_findingstatus CHECK (status IN ('OPEN', 'UNDER_REVIEW', 'RESOLVED', 'DISMISSED')), 
	CONSTRAINT ck_findings_evidencestatus CHECK (evidence_status IN ('VERIFIED', 'UNVERIFIED', 'CONFLICTING', 'INSUFFICIENT'))
);

CREATE INDEX ix_findings_case_id ON findings (case_id);

CREATE TABLE challenges (
	case_id CHAR(32) NOT NULL, 
	finding_id CHAR(32) NOT NULL, 
	status VARCHAR(6) NOT NULL, 
	question TEXT NOT NULL, 
	risk_rationale TEXT NOT NULL, 
	requested_evidence_json JSON NOT NULL, 
	ai_execution_id CHAR(32), 
	human_edits BOOLEAN NOT NULL, 
	id CHAR(32) NOT NULL, 
	version INTEGER NOT NULL, 
	updated_at DATETIME NOT NULL, 
	created_at DATETIME NOT NULL, 
	deleted_at DATETIME, 
	CONSTRAINT pk_challenges PRIMARY KEY (id), 
	CONSTRAINT ck_challenges_positive_version CHECK (version >= 1), 
	CONSTRAINT fk_challenges_case_id_cases FOREIGN KEY(case_id) REFERENCES cases (id), 
	CONSTRAINT fk_challenges_finding_id_findings FOREIGN KEY(finding_id) REFERENCES findings (id), 
	CONSTRAINT ck_challenges_challengestatus CHECK (status IN ('DRAFT', 'READY', 'CLOSED')), 
	CONSTRAINT fk_challenges_ai_execution_id_ai_executions FOREIGN KEY(ai_execution_id) REFERENCES ai_executions (id)
);

CREATE TABLE evidence_refs (
	finding_id CHAR(32) NOT NULL, 
	document_id CHAR(32) NOT NULL, 
	page_number INTEGER NOT NULL, 
	excerpt TEXT NOT NULL, 
	verification_status VARCHAR(12) NOT NULL, 
	id CHAR(32) NOT NULL, 
	CONSTRAINT pk_evidence_refs PRIMARY KEY (id), 
	CONSTRAINT ck_evidence_refs_one_based_page CHECK (page_number >= 1), 
	CONSTRAINT fk_evidence_refs_finding_id_findings FOREIGN KEY(finding_id) REFERENCES findings (id), 
	CONSTRAINT fk_evidence_refs_document_id_documents FOREIGN KEY(document_id) REFERENCES documents (id), 
	CONSTRAINT ck_evidence_refs_evidencestatus CHECK (verification_status IN ('VERIFIED', 'UNVERIFIED', 'CONFLICTING', 'INSUFFICIENT'))
);

CREATE TABLE simulations (
	case_id CHAR(32) NOT NULL, 
	finding_id CHAR(32) NOT NULL, 
	engine_version VARCHAR NOT NULL, 
	supplier_data_version VARCHAR NOT NULL, 
	input_snapshot_json JSON NOT NULL, 
	result_json JSON NOT NULL, 
	interpretation TEXT NOT NULL, 
	id CHAR(32) NOT NULL, 
	created_at DATETIME NOT NULL, 
	CONSTRAINT pk_simulations PRIMARY KEY (id), 
	CONSTRAINT fk_simulations_case_id_cases FOREIGN KEY(case_id) REFERENCES cases (id), 
	CONSTRAINT fk_simulations_finding_id_findings FOREIGN KEY(finding_id) REFERENCES findings (id)
);

CREATE TABLE repair_proposals (
	case_id CHAR(32) NOT NULL, 
	finding_id CHAR(32) NOT NULL, 
	status VARCHAR(9) NOT NULL, 
	action_type VARCHAR(27) NOT NULL, 
	before_text TEXT NOT NULL, 
	proposed_text TEXT NOT NULL, 
	justification TEXT NOT NULL, 
	simulation_id CHAR(32), 
	ai_execution_id CHAR(32), 
	human_edits BOOLEAN NOT NULL, 
	id CHAR(32) NOT NULL, 
	version INTEGER NOT NULL, 
	updated_at DATETIME NOT NULL, 
	created_at DATETIME NOT NULL, 
	deleted_at DATETIME, 
	CONSTRAINT pk_repair_proposals PRIMARY KEY (id), 
	CONSTRAINT ck_repair_proposals_positive_version CHECK (version >= 1), 
	CONSTRAINT fk_repair_proposals_case_id_cases FOREIGN KEY(case_id) REFERENCES cases (id), 
	CONSTRAINT fk_repair_proposals_finding_id_findings FOREIGN KEY(finding_id) REFERENCES findings (id), 
	CONSTRAINT ck_repair_proposals_repairstatus CHECK (status IN ('DRAFT', 'SUBMITTED', 'APPROVED', 'REJECTED', 'WITHDRAWN')), 
	CONSTRAINT ck_repair_proposals_repairactiontype CHECK (action_type IN ('REVISE_REQUIREMENT', 'MAINTAIN_WITH_JUSTIFICATION', 'REQUEST_MORE_EVIDENCE')), 
	CONSTRAINT fk_repair_proposals_simulation_id_simulations FOREIGN KEY(simulation_id) REFERENCES simulations (id), 
	CONSTRAINT fk_repair_proposals_ai_execution_id_ai_executions FOREIGN KEY(ai_execution_id) REFERENCES ai_executions (id)
);

CREATE TABLE reviews (
	case_id CHAR(32) NOT NULL, 
	repair_proposal_id CHAR(32) NOT NULL, 
	decision VARCHAR(16) NOT NULL, 
	decision_reason TEXT NOT NULL, 
	review_status VARCHAR NOT NULL, 
	reviewer_actor_id CHAR(32) NOT NULL, 
	reviewer_snapshot_json JSON NOT NULL, 
	assurance_status_after VARCHAR(16) NOT NULL, 
	id CHAR(32) NOT NULL, 
	created_at DATETIME NOT NULL, 
	CONSTRAINT pk_reviews PRIMARY KEY (id), 
	CONSTRAINT ck_reviews_completed_review CHECK (review_status = 'COMPLETED'), 
	CONSTRAINT fk_reviews_case_id_cases FOREIGN KEY(case_id) REFERENCES cases (id), 
	CONSTRAINT fk_reviews_repair_proposal_id_repair_proposals FOREIGN KEY(repair_proposal_id) REFERENCES repair_proposals (id), 
	CONSTRAINT ck_reviews_reviewdecision CHECK (decision IN ('APPROVE_DRAFT', 'REQUEST_REVISION', 'REQUEST_EVIDENCE', 'REJECT_DRAFT')), 
	CONSTRAINT ck_reviews_assurancestatus CHECK (assurance_status_after IN ('ACTION_REQUIRED', 'READY_FOR_REVIEW', 'REVIEW_COMPLETED'))
);

CREATE TRIGGER protect_ai_executions_update BEFORE UPDATE ON ai_executions BEGIN SELECT RAISE(ABORT, 'immutable record'); END;

CREATE TRIGGER protect_ai_executions_delete BEFORE DELETE ON ai_executions BEGIN SELECT RAISE(ABORT, 'immutable record'); END;

CREATE TRIGGER protect_simulations_update BEFORE UPDATE ON simulations BEGIN SELECT RAISE(ABORT, 'immutable record'); END;

CREATE TRIGGER protect_simulations_delete BEFORE DELETE ON simulations BEGIN SELECT RAISE(ABORT, 'immutable record'); END;

CREATE TRIGGER protect_reviews_update BEFORE UPDATE ON reviews BEGIN SELECT RAISE(ABORT, 'immutable record'); END;

CREATE TRIGGER protect_reviews_delete BEFORE DELETE ON reviews BEGIN SELECT RAISE(ABORT, 'immutable record'); END;

CREATE TRIGGER protect_audit_events_update BEFORE UPDATE ON audit_events BEGIN SELECT RAISE(ABORT, 'immutable record'); END;

CREATE TRIGGER protect_audit_events_delete BEFORE DELETE ON audit_events BEGIN SELECT RAISE(ABORT, 'immutable record'); END;
