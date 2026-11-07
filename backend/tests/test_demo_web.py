"""Same-origin deployment composition tests; no provider or finding fallback."""
from uuid import uuid4
from fastapi.testclient import TestClient
from sqlalchemy import text
from app.core.config import Settings
from app.core.database import build_engine
from app.core.demo_bootstrap import bootstrap
from app.web import create_web_app


def test_combined_bootstrap_preserves_guards_and_is_repeatable(tmp_path):
    engine=build_engine('sqlite:///'+(tmp_path/'demo.db').as_posix())
    try:
        bootstrap(engine)
        bootstrap(engine)
        with engine.connect() as connection:
            assert connection.exec_driver_sql('PRAGMA user_version').scalar()==2
            assert connection.exec_driver_sql('PRAGMA foreign_key_check').first() is None
            assert connection.execute(text("SELECT count(*) FROM sqlite_master WHERE type='trigger' AND name='execution_document_same_case_insert'")).scalar()==1
            assert connection.execute(text('SELECT count(*) FROM assurance_schema_revisions')).scalar()==2
    finally: engine.dispose()


def test_web_ui_api_and_owner_acl_ports_share_one_origin(tmp_path):
    url='sqlite:///'+(tmp_path/'demo.db').as_posix()
    engine=build_engine(url);bootstrap(engine);engine.dispose()
    static=tmp_path/'dist';static.mkdir();(static/'index.html').write_text('<html>Test-only static fixture</html>')
    scopes={'case:write','case:read','simulation:read','simulation:write','audit:read'}
    config=Settings(database_url=url,demo_mode=True,demo_actor_id=uuid4(),demo_scopes=frozenset(scopes))
    with TestClient(create_web_app(config,static)) as client:
        assert client.get('/').status_code==200
        assert client.get('/api/v1/health').json()['data']['demo_mode'] is True
        response=client.post('/api/v1/cases',headers={'Idempotency-Key':'demo-test'},json={'title':'Demo connectivity','category':'OTHER','quantity':1,'budget_ceiling_idr':0})
        assert response.status_code==201,response.text
        cid=response.json()['data']['case_id']
        assert client.get(f'/api/v1/cases/{cid}/simulations').json()['data']['items']==[]
        timeline=client.get(f'/api/v1/cases/{cid}/audit')
        assert timeline.status_code==200,timeline.text
        assert timeline.json()['data']['items'][0]['event_type']=='CASE_CREATED'
        assert timeline.json()['data']['items'][0]['event_hash'] is None
        assert timeline.json()['data']['items'][0]['previous_hash'] is None
        bad=client.post(f'/api/v1/cases/{cid}/simulations',headers={'Idempotency-Key':'missing-finding'},json={'finding_id':str(uuid4()),'baseline':{'minimum_ram_gb':32},'alternative':{'minimum_ram_gb':16},'supplier_data_version':'synthetic-suppliers-v1'})
        assert bad.status_code==404,bad.text
