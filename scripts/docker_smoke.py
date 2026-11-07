"""Explicit synthetic Docker persistence check. Never calls an AI provider.

Run create, recreate the container (without deleting its volume), then verify.
Credentials are read from environment/.env and never written to the state file.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import tempfile
import time
from uuid import uuid4

import httpx
import pymupdf
from dotenv import dotenv_values


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('phase', choices=['create', 'verify'])
    parser.add_argument('--url', default='http://127.0.0.1:18000')
    parser.add_argument('--state', type=Path, default=Path(tempfile.gettempdir()) / 'procuremind-docker-smoke.json')
    args = parser.parse_args()
    config = {**dotenv_values(Path(__file__).resolve().parents[1] / '.env', interpolate=False), **os.environ}
    with httpx.Client(base_url=args.url, timeout=30) as client:
        for attempt in range(30):
            try:
                if client.get('/api/v1/health').status_code == 200:
                    break
            except httpx.TransportError:
                pass
            time.sleep(1)
        else:
            raise RuntimeError('Docker health did not become ready')
        assert client.get('/api/v1/cases').status_code == 401
        response = client.post('/auth/login', json={'username': config.get('PROCUREMIND_LOGIN_USERNAME', 'admin'),
                                                   'password': config['PROCUREMIND_LOGIN_PASSWORD']})
        assert response.status_code == 200, 'Login failed'
        if args.phase == 'create':
            response = client.post('/api/v1/cases', headers={'Idempotency-Key': str(uuid4())}, json={
                'title': 'SYNTHETIC Docker persistence check', 'category': 'IT_EQUIPMENT',
                'description': 'Isolated automated deployment test; no live AI output.', 'quantity': 50, 'budget_ceiling_idr': 900000000})
            assert response.status_code == 201, response.text
            cid = response.json()['data']['case_id']
            with pymupdf.open() as pdf:
                pdf.new_page().insert_text((72,72), 'SYNTHETIC local deployment document: minimum RAM 16 GB')
                payload = pdf.tobytes()
            documents = []
            for index in range(2):
                response = client.post(f'/api/v1/cases/{cid}/documents', headers={'Idempotency-Key': str(uuid4())},
                    files={'file': (f'synthetic-docker-{index}.pdf', payload, 'application/pdf')}, data={'document_type': 'OTHER'})
                assert response.status_code == 201, response.text
                documents.append(response.json()['data'])
            did = documents[0]['document_id']
            response = client.patch(f'/api/v1/documents/{did}', json={'document_type': 'TOR', 'expected_version': 1})
            assert response.status_code == 200, response.text
            removed = documents[1]['document_id']
            response = client.request('DELETE', f'/api/v1/documents/{removed}', json={'reason': 'Synthetic wrong upload test', 'expected_version': 1})
            assert response.status_code == 200, response.text
            args.state.write_text(json.dumps({'case_id': cid, 'kept': did, 'removed': removed,
                                              'sha256': hashlib.sha256(payload).hexdigest()}))
            print('PASS: login, case creation, two PDF uploads, type change and soft delete')
        state = json.loads(args.state.read_text())
        cid = state['case_id']
        assert client.get(f'/api/v1/cases/{cid}').status_code == 200
        cases = client.get('/api/v1/cases?limit=100').json()['data']['items']
        assert any(case['case_id'] == cid for case in cases)
        documents = client.get(f'/api/v1/cases/{cid}/documents').json()['data']['items']
        assert len(documents) == 1 and documents[0]['document_id'] == state['kept']
        assert documents[0]['document_type'] == 'TOR' and documents[0]['sha256'] == state['sha256']
        assert client.get(f"/api/v1/documents/{state['removed']}").status_code == 404
        audit = client.get(f'/api/v1/cases/{cid}/audit').json()['data']['items']
        assert any(event['event_type'] == 'DOCUMENT_DELETED' for event in audit)
        assert client.post('/auth/logout').status_code == 200
        assert client.get('/api/v1/cases').status_code == 401
        print('PASS: authorized case history, retained metadata/hash, deleted-row exclusion, audit and logout')


if __name__ == '__main__':
    main()
