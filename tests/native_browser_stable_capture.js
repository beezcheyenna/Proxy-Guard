async page => {
 const result={ok:false,pages:[],errors:[]};const fail=e=>result.errors.push(String(e));page.on('pageerror',fail);
 try {
  for(const row of [{lang:'zh-cn',locale:'zh-CN',heading:'VPS 访问规则'},{lang:'ja',locale:'ja-JP',heading:'VPS アクセスルール'}]){
   await page.context().setExtraHTTPHeaders({'Accept-Language':row.locale+','+row.lang+';q=0.9,en;q=0.5'});
   await page.goto('http://10.77.0.1/cgi-bin/luci/admin/services/proxy-guard-access',{waitUntil:'domcontentloaded',timeout:90000});
   await page.getByRole('heading',{name:row.heading,exact:true}).waitFor({state:'visible',timeout:60000});
   const before=await page.evaluate(()=>({fonts:document.fonts.status,heading:document.querySelector('h2').textContent}));
   await page.evaluate(async()=>{await document.fonts.ready;await new Promise(requestAnimationFrame);await new Promise(requestAnimationFrame);});
   await page.waitForFunction(()=>Array.from(document.querySelectorAll('a')).some(a=>/\/admin\/status(?:\/|$)/.test(a.href)&&a.getBoundingClientRect().height>0),{timeout:30000});
   const after=await page.evaluate(()=>({fonts:document.fonts.status,heading:document.querySelector('h2').textContent,headingFont:getComputedStyle(document.querySelector('h2')).fontFamily,fontFaces:Array.from(document.fonts,f=>({family:f.family,status:f.status})),navLinks:Array.from(document.querySelectorAll('a')).filter(a=>/\/admin\//.test(a.href)).length}));
   const screenshot='/opt/pg-browser/output/playwright/stable-'+row.lang+'-pro.png';
   await page.screenshot({path:screenshot,fullPage:true});
   result.pages.push({lang:row.lang,before,after,screenshot});
  }
  result.ok=result.errors.length===0;return result;
 }finally{page.off('pageerror',fail);}
}
