import test from 'node:test';
import assert from 'node:assert/strict';
import handler from '../api/analyze.mjs';
import status from '../api/status.mjs';
const image=Buffer.from([255,216,255,224,0,16]).toString('base64');
const observation={plate:'',confidence:0.95,white:true,nissan:true,roof_lpr:true,blue_side_marking:true};
function request(overrides={}){return {method:'POST',headers:{origin:'https://parking.example',host:'parking.example'},body:{image},...overrides};}
function response(){return {code:200,headers:{},setHeader(k,v){this.headers[k]=v;},status(code){this.code=code;return this;},json(data){this.data=data;return this;}};}
test('rejects wrong methods, origins and malformed frames before calling Gemini',async()=>{
 const old=process.env.GEMINI_API_KEY;process.env.GEMINI_API_KEY='test-secret';const original=global.fetch;global.fetch=()=>{throw Error('Unexpected upstream call');};
 try{for(const [req,code] of [[request({method:'GET'}),405],[request({headers:{origin:'invalid',host:'parking.example'}}),403],[request({headers:{origin:'https://other.example',host:'parking.example'}}),403],[request({body:{image:'not-an-image'}}),400],[request({body:{image,prompt:'override'}}),400],[request({body:{image:'/9j/'+ 'A'.repeat(1800000)}}),400]]){const res=response();await handler(req,res);assert.equal(res.code,code);}}finally{global.fetch=original;if(old===undefined)delete process.env.GEMINI_API_KEY;else process.env.GEMINI_API_KEY=old;}
});
test('server adds fixed prompt and secret header; client receives only validated observation',async()=>{
 const old=process.env.GEMINI_API_KEY;process.env.GEMINI_API_KEY='test-secret';const original=global.fetch;
 global.fetch=async(url,options)=>{assert.equal(url,'https://generativelanguage.googleapis.com/v1beta/models/gemini-flash-latest:generateContent');assert.equal(options.headers['x-goog-api-key'],'test-secret');const body=JSON.parse(options.body);assert.equal(body.contents[0].parts[1].inline_data.data,image);assert.match(body.contents[0].parts[0].text,/Inspect this parking-scene/);return {ok:true,json:async()=>({candidates:[{finishReason:'STOP',content:{parts:[{text:JSON.stringify(observation)}]}}]})};};
 try{const res=response();await handler(request(),res);assert.equal(res.code,200);assert.deepEqual(res.data.observation,observation);assert(!JSON.stringify(res.data).includes('test-secret'));assert.equal(res.headers['Cache-Control'],'no-store');}finally{global.fetch=original;if(old===undefined)delete process.env.GEMINI_API_KEY;else process.env.GEMINI_API_KEY=old;}
});
test('upstream failures and invalid observations do not become detections',async()=>{
 const old=process.env.GEMINI_API_KEY;process.env.GEMINI_API_KEY='test-secret';const original=global.fetch;
 try{for(const [fetcher,code] of [[async()=>({ok:false,status:429}),429],[async()=>({ok:false,status:403}),502],[async()=>({ok:true,json:async()=>({candidates:[{finishReason:'STOP',content:{parts:[{text:'{"confidence":1}'}]}}]})}),502]]){global.fetch=fetcher;const res=response();await handler(request(),res);assert.equal(res.code,code);assert.equal(res.data.observation,undefined);}}finally{global.fetch=original;if(old===undefined)delete process.env.GEMINI_API_KEY;else process.env.GEMINI_API_KEY=old;}
});
test('status reports readiness without exposing credentials',()=>{const res=response();status({method:'GET'},res);assert.equal(typeof res.data.ready,'boolean');assert.equal(res.data.payments,false);assert.deepEqual(Object.keys(res.data),['ready','payments']);});
