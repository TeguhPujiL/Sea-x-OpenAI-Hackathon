import test from 'node:test';
import assert from 'node:assert/strict';
import React from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import {classifyBatch,decodeClassification} from '../src/classification.ts';
import {newUploadItems} from '../src/uploads.ts';
import {createClient,requiresIdempotency,readConfig} from '../src/api.ts';
import {documentTypes,ShapeError} from '../src/contracts.ts';
import {DocumentUploads,DocumentTypeEditor} from '../src/DocumentUploads.tsx';
import {saveDocumentTypes} from '../src/documentTypes.ts';
import {documentResource,IDs,envelope,errorEnvelope} from './fixtures.mjs';

const config={baseUrl:'/api/v1',development:true};
const noop=()=>{};
const signal=()=>new AbortController().signal;
const item=()=>({...newUploadItems([new File(['%PDF-fixture'],'misleading-contract.pdf',{type:'application/pdf'})],'')[0],status:'uploaded',document:{...documentResource('OTHER'),document_id:crypto.randomUUID()}});
function proposal(document,kind='TOR',status='AUTO_READY') {return {document_id:document.document_id,case_id:IDs.case,expected_version:document.version,suggested_type:kind,confidence:.98,status,rationale:'Test-only grounded primary purpose.',evidence:[{document_id:document.document_id,page_number:1,excerpt:'TERMS OF REFERENCE',verification_status:'VERIFIED'}],ai_execution_id:IDs.ai};}

test('nine-type batch applies only ready results with bounded concurrency and expected_version',async()=>{
  const items=documentTypes.map(()=>item());const byId=new Map(items.map((it,i)=>[it.document.document_id,{doc:it.document,kind:documentTypes[i]}]));
  const calls=[];let active=0,maxActive=0;
  const client=createClient(config,async(url,init)=>{
    calls.push({url,...init});const id=url.split('/')[4];const {doc,kind}=byId.get(id);
    if(url.endsWith('/classifications')){
      active++;maxActive=Math.max(maxActive,active);await new Promise(resolve=>setTimeout(resolve,5));active--;
      assert.ok(init.headers['Idempotency-Key']);
      return Response.json(envelope(proposal(doc,kind,kind==='OTHER'?'NEEDS_REVIEW':'AUTO_READY')),{status:201});
    }
    assert.equal(init.method,'PATCH');const body=JSON.parse(init.body);assert.equal(body.expected_version,1);
    return Response.json(envelope({...doc,document_type:body.document_type,version:2}));
  });
  const saved=[];const result=await classifyBatch(client,IDs.case,items,noop,d=>saved.push(d),signal());
  assert.equal(maxActive,2);assert.equal(saved.length,8);
  assert.equal(result.filter(i=>i.classificationStatus==='ready').length,8);
  assert.equal(result.find(i=>i.classification.suggested_type==='OTHER').classificationStatus,'needs_review');
  assert.equal(calls.filter(c=>c.method==='POST'&&!c.url.endsWith('/classifications')).length,0);
});

test('classification transport retry reuses its key and never uploads the PDF again',async()=>{
  const entry=item();let count=0;const keys=[];
  const client=createClient(config,async(url,init)=>{
    if(url.endsWith('/classifications')){keys.push(init.headers['Idempotency-Key']);if(!count++)throw new TypeError('test network interruption');return Response.json(envelope(proposal(entry.document)),{status:201});}
    assert.equal(init.method,'PATCH');return Response.json(envelope({...entry.document,document_type:'TOR',version:2}));
  });
  const first=await classifyBatch(client,IDs.case,[entry],noop,noop,signal());
  assert.equal(first[0].status,'uploaded');assert.equal(first[0].classificationStatus,'unknown');
  const second=await classifyBatch(client,IDs.case,first,noop,noop,signal());
  assert.equal(second[0].classificationStatus,'ready');assert.equal(keys[0],keys[1]);
});

test('provider failure retains uploaded file and can retry classification without reupload',async()=>{
  const entry=item();let count=0;
  const client=createClient(config,async(url,init)=>{
    if(url.endsWith('/classifications'))return !count++?Response.json(errorEnvelope('AI_PROVIDER_TIMEOUT','Timeout',true),{status:504}):Response.json(envelope(proposal(entry.document)),{status:201});
    assert.equal(init.method,'PATCH');return Response.json(envelope({...entry.document,document_type:'TOR',version:2}));
  });
  const first=await classifyBatch(client,IDs.case,[entry],noop,noop,signal());assert.equal(first[0].status,'uploaded');assert.equal(first[0].classificationStatus,'failed');
  const second=await classifyBatch(client,IDs.case,first,noop,noop,signal());assert.equal(second[0].classificationStatus,'ready');
});

test('cross-case and unverified confident responses cannot trigger a metadata PATCH',async()=>{
  const entry=item();let patches=0;
  const client=createClient(config,async(url,init)=>{if(init.method==='PATCH')patches++;return Response.json(envelope({...proposal(entry.document),case_id:IDs.actor}),{status:201});});
  const result=await classifyBatch(client,IDs.case,[entry],noop,noop,signal());assert.equal(result[0].classificationStatus,'failed');assert.equal(patches,0);
  assert.throws(()=>decodeClassification({...proposal(entry.document),evidence:[]}),ShapeError);
  assert.throws(()=>decodeClassification({...proposal(entry.document),suggested_type:'OTHER'}),ShapeError);
});

test('version conflict preserves a newer human-selected document type',async()=>{
  const entry=item();let patches=0;const newer={...entry.document,document_type:'CONTRACT',version:2};const saved=[];
  const client=createClient(config,async(url,init)=>{
    if(url.endsWith('/classifications'))return Response.json(envelope(proposal(entry.document)),{status:201});
    if(init.method==='PATCH'){patches++;return Response.json(errorEnvelope('VERSION_CONFLICT','Newer document',false),{status:409});}
    return Response.json(envelope(newer));
  });
  const result=await classifyBatch(client,IDs.case,[entry],noop,d=>saved.push(d),signal());
  assert.equal(result[0].classificationStatus,'needs_review');assert.equal(result[0].document.document_type,'CONTRACT');assert.equal(patches,1);assert.equal(saved[0].document_type,'CONTRACT');
});

test('batch UI explains automatic assignment, uncertainty and evidence without promising accuracy',()=>{
  const entry=item();entry.classification=proposal(entry.document,'OTHER','NEEDS_REVIEW');entry.classificationStatus='needs_review';
  const html=renderToStaticMarkup(React.createElement(DocumentUploads,{disabled:false,items:[entry],autoClassify:true,onUpload:noop,onRetry:noop,onClear:noop}));
  assert.match(html,/nine document types/);assert.match(html,/No uncertain type was automatically applied/);assert.match(html,/Classification evidence/);
  assert.equal(requiresIdempotency('POST',`/documents/${entry.document.document_id}/classifications`),true);
  assert.equal(readConfig({DEV:true,VITE_DOCUMENT_CLASSIFICATION_ENABLED:'true'}).classifyDocuments,true);
});

test('a person can confirm OTHER without changing it, using an audited versioned PATCH',async()=>{
  const doc=documentResource('OTHER');const calls=[];
  const client=createClient(config,async(url,init)=>{calls.push(JSON.parse(init.body));return Response.json(envelope({...doc,version:2}));});
  await saveDocumentTypes(client,[doc],{[doc.document_id]:'OTHER'},noop,signal());assert.equal(calls.length,0);
  await saveDocumentTypes(client,[doc],{[doc.document_id]:'OTHER'},noop,signal(),new Set([doc.document_id]));
  assert.deepEqual(calls,[{document_type:'OTHER',expected_version:1}]);
  const html=renderToStaticMarkup(React.createElement(DocumentTypeEditor,{document:doc,disabled:false,requiresConfirmation:true,onChange:noop}));
  assert.match(html,/Confirm selected type/);
});
