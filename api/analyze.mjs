import {prompt,schema} from '../lib/vision.mjs';
export default async function handler(req,res){
  res.setHeader('Cache-Control','no-store');
  if(req.method!=='POST')return res.status(405).json({error:'POST required'});
  let originHost;try{originHost=new URL(req.headers.origin).host;}catch{}
  if(!originHost || originHost!==req.headers.host)return res.status(403).json({error:'Open the video preview to analyze frames'});
  if(!process.env.GEMINI_API_KEY)return res.status(503).json({error:'Detection is not configured on the server'});
  const body=req.body;
  if(!body || typeof body!=='object' || Object.keys(body).length!==1 || typeof body.image!=='string' || body.image.length>1800000 || !/^\/9j\/[A-Za-z0-9+/]*={0,2}$/.test(body.image))return res.status(400).json({error:'Send one JPEG frame, up to 1.3 MB'});
  const started=Date.now();
  try{
    const response=await fetch('https://generativelanguage.googleapis.com/v1beta/models/gemini-flash-latest:generateContent',{
      method:'POST',headers:{'Content-Type':'application/json','x-goog-api-key':process.env.GEMINI_API_KEY},signal:AbortSignal.timeout(30000),
      body:JSON.stringify({contents:[{role:'user',parts:[{text:prompt},{inline_data:{mime_type:'image/jpeg',data:body.image}}]}],generationConfig:{temperature:0,responseMimeType:'application/json',responseJsonSchema:schema}})
    });
    if(!response.ok)return res.status(response.status===429?429:502).json({error:response.status===429?'Detection quota reached. Try later.':'Vision service could not analyze this frame'});
    const data=await response.json(),candidate=data.candidates?.[0];
    if(candidate?.finishReason!=='STOP')throw Error('Incomplete result');
    const text=(candidate.content?.parts||[]).filter(p=>!p.thought&&typeof p.text==='string').map(p=>p.text).join('');
    const observation=JSON.parse(text);
    if(!observation || Object.keys(observation).sort().join(',')!==schema.required.slice().sort().join(',') || typeof observation.plate!=='string' || observation.plate.length>32 || !Number.isFinite(observation.confidence)||observation.confidence<0||observation.confidence>1 || ['white','nissan','roof_lpr','blue_side_marking'].some(f=>typeof observation[f]!=='boolean'))throw Error('Invalid result');
    return res.status(200).json({observation,latencyMs:Date.now()-started});
  }catch(error){
    return res.status(error.name==='TimeoutError'?504:502).json({error:error.name==='TimeoutError'?'Frame analysis timed out':'Vision service returned an invalid result'});
  }
}
