import {mkdir,copyFile,rm} from 'node:fs/promises';
await rm('public',{recursive:true,force:true});
await mkdir('public/parking_sentinel/media',{recursive:true});
await copyFile('parking-preview.html','public/index.html');
await copyFile('parking-preview.html','public/parking-preview.html');
await copyFile('parking_sentinel/media/parking-enforcement-staged-60s.mp4','public/parking_sentinel/media/parking-enforcement-staged-60s.mp4');
