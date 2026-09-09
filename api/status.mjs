export default function handler(req,res){
  res.setHeader('Cache-Control','no-store');
  if(req.method!=='GET')return res.status(405).json({error:'GET required'});
  res.status(200).json({ready:Boolean(process.env.GEMINI_API_KEY),payments:false});
}
