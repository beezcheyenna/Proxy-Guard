async page => {
 const row=ROW, result={lang:row.lang,selection:'explicit LuCI language',pages:[],errors:[]};
 const error=e=>result.errors.push(String(e));page.on('pageerror',error);
 try {
  await page.context().setExtraHTTPHeaders({'Accept-Language':row.locale+','+row.lang+';q=0.9,en;q=0.5'});
  for(const kind of (row.kind?[row.kind]:['standard','pro'])){
   await page.goto('http://10.77.0.1/cgi-bin/luci/admin/services/'+(kind==='standard'?'proxy-guard':'proxy-guard-access'),{waitUntil:'domcontentloaded',timeout:90000});
   if(kind==='standard')await page.getByText(row.label,{exact:true}).first().waitFor({state:'visible',timeout:60000});
   else await page.getByRole('heading',{name:row.heading,exact:true}).waitFor({state:'visible',timeout:60000});
   await page.evaluate(async()=>{await document.fonts.ready;await new Promise(requestAnimationFrame);await new Promise(requestAnimationFrame);});
   await page.waitForFunction(()=>Array.from(document.querySelectorAll('a')).some(a=>/\/admin\/(?:status(?:\/|$)|logout(?:\/|$))/.test(a.href)&&a.getBoundingClientRect().height>0),null,{timeout:30000});
   const dom=await page.evaluate(()=>({
    htmlLang:document.documentElement.lang,
    directions:Array.from(document.querySelectorAll('.pg-guard'),e=>getComputedStyle(e).direction),
    fields:Array.from(document.querySelectorAll('.pg-guard input,.pg-guard textarea')).filter(e=>/(?:sources[46]|local[46]|exit_url|exit_fallback_url|expected_exit4|endpoint|interfaces|udp_server)$/.test(e.id)).map(e=>({id:e.id,dir:e.dir})),
    width:innerWidth,scrollWidth:document.documentElement.scrollWidth,
    headings:Array.from(document.querySelectorAll('h2'),e=>e.textContent),
    fonts:document.fonts.status,controls:document.querySelectorAll('.pg-guard input,.pg-guard button,.pg-guard select').length,
    fontFaces:Array.from(document.fonts,f=>({family:f.family,status:f.status}))
   }));
   if(!dom.htmlLang.startsWith(row.lang==='zh-cn'?'zh':row.lang))throw Error('wrong document language '+JSON.stringify(dom));
   if(dom.directions.some(x=>x!==(row.lang==='fa'?'rtl':'ltr'))||!dom.directions.length)throw Error('wrong writing direction');
   if(row.lang==='fa'&&dom.fields.some(x=>x.dir!=='ltr'))throw Error('machine values must stay left-to-right');
   const screenshot='/opt/pg-browser/output/playwright/'+(row.prefix||'explicit-')+row.lang+'-'+kind+'.png';
   await page.screenshot({path:screenshot,fullPage:false,animations:'disabled',timeout:90000});
   result.pages.push({kind,...dom,screenshot});
  }
  result.ok=result.errors.length===0;return result;
 }finally{page.off('pageerror',error);}
}