import http from 'node:http';
import {readFile,stat} from 'node:fs/promises';
import {createReadStream} from 'node:fs';
import path from 'node:path';
import analyze from '../api/analyze.mjs';
import status from '../api/status.mjs';
const root=process.cwd(),port=Number(process.env.PORT||8765);
http.createServer(async(req,res)=>{
  res.status=code=>{res.statusCode=code;return res;};res.json=data=>{res.setHeader('Content-Type','application/json');res.end(JSON.stringify(data));};
  if(!['127.0.0.1:'+port,'localhost:'+port].includes(req.headers.host))return res.status(403).json({error:'Loopback host required'});
  try{
    const route=new URL(req.url,'http://localhost').pathname;
    if(route==='/api/status')return status(req,res);
    if(route==='/api/analyze'){
      let size=0,chunks=[];for await(const chunk of req){size+=chunk.length;if(size>1850000)return res.status(413).json({error:'Frame too large'});chunks.push(chunk);}
      try{req.body=JSON.parse(Buffer.concat(chunks).toString());}catch{return res.status(400).json({error:'Invalid JSON'});}
      return await analyze(req,res);
    }
    if(req.method!=='GET'&&req.method!=='HEAD')return res.status(405).json({error:'Method not allowed'});
    let file;
    if(route==='/'||route==='/parking-preview.html')file='parking-preview.html';
    else if(['/parking_sentinel/media/parking-enforcement-staged-60s.mp4','/parking_sentinel/media/stationary-preview.mp4'].includes(route))file=route.slice(1);
    else return res.status(404).json({error:'Not found'});
    const full=path.join(root,file),info=await stat(full);res.setHeader('Cache-Control','no-store');res.setHeader('Content-Type',file.endsWith('.mp4')?'video/mp4':'text/html; charset=utf-8');
    if(!file.endsWith('.mp4'))return res.end(await readFile(full));
    let start=0,end=info.size-1;res.setHeader('Accept-Ranges','bytes');
    if(req.headers.range){const match=/^bytes=(\d*)-(\d*)$/.exec(req.headers.range);if(!match||(!match[1]&&!match[2]))return res.status(416).end();if(match[1]){start=Number(match[1]);if(match[2])end=Math.min(end,Number(match[2]));}else start=Math.max(0,info.size-Number(match[2]));if(start>end||start>=info.size)return res.status(416).end();res.statusCode=206;res.setHeader('Content-Range',`bytes ${start}-${end}/${info.size}`);}
    res.setHeader('Content-Length',end-start+1);if(req.method==='HEAD')return res.end();createReadStream(full,{start,end}).pipe(res);
  }catch{if(!res.headersSent)res.status(500).json({error:'Unable to serve request'});else res.end();}
}).listen(port,'127.0.0.1',()=>console.log(`Parking Sentinel: http://127.0.0.1:${port}`));
