function l(n){const t=n.trim();if(!t||/[\r\n]/.test(t))return null;try{const r=new URL(t);return r.protocol==="http:"||r.protocol==="https:"?r.href:null}catch{return null}}export{l as s};
