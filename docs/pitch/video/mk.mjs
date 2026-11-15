const P=[[2.9,1300,215],[3.0,1269,233],[3.25,1249,260],[3.5,1216,273],[3.75,1167,267],[4.0,1133,260],[4.5,1120,233],[5.0,1131,220],[5.5,1127,200],[5.75,1127,197],[6.0,1127,180],[6.25,1107,67],[6.45,1095,-40]];
const W=108,H=92;
function pw(i){let e=String(P[P.length-1][i]);for(let k=P.length-2;k>=0;k--){const[a,b]=[P[k],P[k+1]];e=`if(lt(t,${b[0]}),${a[i]}+(${b[i]}-${a[i]})*(t-${a[0]})/${(b[0]-a[0]).toFixed(3)},${e})`;}return e;}
const X=`min(max(${pw(1)}-${W/2},0),${1280-W})`, Y=`min(max(${pw(2)}-${H/2},0),${720-H})`;
const font="C\\:/Windows/Fonts/arial.ttf";
const fc=`[0:v]split[a][b];[b]crop=${W}:${H}:'${X}':'${Y}',boxblur=14:3[c];[a][c]overlay=x='${X}':y='${Y}':enable='between(t,2.9,6.45)',drawtext=fontfile='${font}':text='Yapay zekâ ile üretildi (Google Gemini)':x=w-tw-18:y=h-th-16:fontsize=22:fontcolor=white@0.85:box=1:boxcolor=black@0.45:boxborderw=8[v]`;
(await import('node:fs')).writeFileSync('fc.txt',fc);
