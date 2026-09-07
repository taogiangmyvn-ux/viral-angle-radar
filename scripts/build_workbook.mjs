import fs from "node:fs/promises";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const [inputPath, outputPath] = process.argv.slice(2);
if (!inputPath || !outputPath) throw new Error("Usage: node scripts/build_workbook.mjs input.json output.xlsx");
const data = JSON.parse(await fs.readFile(inputPath, "utf8"));
const wb = Workbook.create();
const names = ["Top Videos","Angle Radar","Q4 Playbook","Creators","Metric History","Brand Relevance","Generated Briefs","Data Quality","Run Log"];
const sheets = Object.fromEntries(names.map(name=>[name,wb.worksheets.add(name)]));
const headerFill="#342A22", headerFont="#FFFFFF", accent="#D8C2A5", green="#2F6B55", line="#DDD5CB";
function title(sheet,text,subtitle){sheet.showGridLines=false;sheet.getRange("A1").values=[[text]];sheet.getRange("A1").format.font={bold:true,size:18,color:"#2B241F",name:"Arial"};sheet.getRange("A2").values=[[subtitle]];sheet.getRange("A2").format.font={italic:true,size:10,color:"#746A61",name:"Arial"};}
function tableStyle(sheet,range,header){sheet.getRange(range).format.font={name:"Arial",size:10,color:"#2B241F"};sheet.getRange(range).format.borders={bottom:{style:"thin",color:line}};sheet.getRange(header).format.fill=headerFill;sheet.getRange(header).format.font={bold:true,color:headerFont,name:"Arial",size:10};sheet.getRange(header).format.wrapText=true;sheet.getRange(header).format.verticalAlignment="center";}
function scoreFormat(range){range.setNumberFormat("0");range.conditionalFormats.add("colorScale",{colors:["#F4D8D2","#F5E7C8","#D9EBDD"],thresholds:["min",{type:"percentile",value:50},"max"]});}

const top=sheets["Top Videos"];title(top,"CoBa's Daughter opportunity radar",`US bodycare and Q4 gifting sources. Generated ${data.generated_at}.`);
const vh=["Opportunity","Brand fit","Q4 potential","Gifting","Momentum","Creator","TikTok source","Published","Angle","Q4 pillars","Format","Hook","Likes","Evidence","Why it fits"];
top.getRange("A4:O4").values=[vh];
const videoRows=data.videos.map(v=>[v.trend_score,v.brand_fit_score,v.q4_potential_score,v.gifting_relevance_score,v.momentum_score,v.creator_name,v.canonical_url,v.published_at,v.primary_angle,v.q4_pillars,v.format,v.hook_summary,v.likes,v.evidence_quality,v.explanation]);
if(videoRows.length)top.getRange("A5").write(videoRows);tableStyle(top,`A4:O${4+Math.max(1,videoRows.length)}`,"A4:O4");top.freezePanes.freezeRows(4);scoreFormat(top.getRange("A5:E200"));top.getRange("M:M").setNumberFormat("#,##0");
for(const [cols,width] of [["A:E",13],["F:F",22],["G:G",48],["H:H",14],["I:K",23],["L:L",55],["M:N",13],["O:O",60]])top.getRange(cols).format.columnWidth=width;

const ar=sheets["Angle Radar"];title(ar,"Angle radar","Compare opportunity with CoBa's Daughter fit, Q4 timing and gifting relevance.");
ar.getRange("A4:H4").values=[["Angle","Sources","Median opportunity","Max opportunity","Median brand fit","Median Q4","Median gifting","Representative source"]];
const angleRows=data.angles.map(a=>[a.angle,a.video_count,a.median_score,a.max_score,a.median_brand_fit,a.median_q4_potential,a.median_gifting_relevance,a.representative_url]);
if(angleRows.length)ar.getRange("A5").write(angleRows);tableStyle(ar,`A4:H${4+Math.max(1,angleRows.length)}`,"A4:H4");ar.freezePanes.freezeRows(4);scoreFormat(ar.getRange("C5:G200"));ar.getRange("A:G").format.autofitColumns();ar.getRange("H:H").format.columnWidth=55;

const q4=sheets["Q4 Playbook"];title(q4,"Q4 content playbook","Public-safe summary derived from the supplied brand materials; internal commercial figures are excluded.");
q4.getRange("A4:E4").values=[["Month","Priority","Pillar mix","Best source pattern","Native-US brief direction"]];
q4.getRange("A5:E8").values=[
  ["September","Tease and get indexed","Gift Guide 45%; Keepsake 25%; Aesop Alternative 20%; Occasion 10%","Early gift-guide search and beautiful object reveal","I found the bodycare gift that looks considered before you even open it."],
  ["October","Scale into guides","Gift Guide 40%; Aesop Alternative 25%; Keepsake 20%; Occasion 15%","Under-$100 roundup and luxury-alternative verdict","If she loves Aesop-level taste, this Vietnamese bodycare ritual is the unexpected pick."],
  ["November","Convert around hosting","Occasion 35%; Gift Guide 25%; Aesop Alternative 25%; Keepsake 15%","Hostess, Friendsgiving and woman-who-has-everything","What do you bring the host who notices every detail?"],
  ["December","Harvest and be remembered","Occasion 45%; Keepsake 30%; Gift Guide 15%; Aesop Alternative 10%","Gift-or-keep unboxing and last-ship urgency","I bought one to gift and one to keep—the handwoven case decided it."]
];tableStyle(q4,"A4:E8","A4:E4");q4.getRange("A:A").format.columnWidth=15;q4.getRange("B:B").format.columnWidth=25;q4.getRange("C:C").format.columnWidth=56;q4.getRange("D:E").format.columnWidth=55;q4.getRange("A4:E8").format.wrapText=true;

const creators=sheets["Creators"];title(creators,"US creator evidence","Location and source coverage used by the scoring model.");
creators.getRange("A4:E4").values=[["Creator","Handle","Country","Country evidence","Sources"]];const counts=new Map();for(const v of data.videos){const k=v.creator_handle||v.creator_name;const old=counts.get(k)||{name:v.creator_name,handle:v.creator_handle,country:v.creator_country,evidence:v.creator_country_evidence,count:0};old.count++;counts.set(k,old)}const creatorRows=[...counts.values()].map(x=>[x.name,x.handle,x.country,x.evidence,x.count]);if(creatorRows.length)creators.getRange("A5").write(creatorRows);tableStyle(creators,`A4:E${4+Math.max(1,creatorRows.length)}`,"A4:E4");creators.getRange("A:C").format.autofitColumns();creators.getRange("D:D").format.columnWidth=55;

const metrics=sheets["Metric History"];title(metrics,"Metric history","Latest normalized observation. Missing view counts remain blank; observed likes are never relabeled as views.");
metrics.getRange("A4:H4").values=[["Video ID","Published","Views","Likes","Comments","Shares","Followers","Source"]];const metricRows=data.videos.map(v=>["'"+v.video_id,v.published_at,v.views,v.likes,v.comments,v.shares,v.followers,v.source_provider]);if(metricRows.length)metrics.getRange("A5").write(metricRows);tableStyle(metrics,`A4:H${4+Math.max(1,metricRows.length)}`,"A4:H4");metrics.getRange("A:H").format.autofitColumns();metrics.getRange("C:G").setNumberFormat("#,##0");
metrics.getRange("A5:A200").setNumberFormat("@");metrics.getRange("A:A").format.columnWidth=24;

const relevance=sheets["Brand Relevance"];title(relevance,"Brand relevance","Auditable fit notes for each source. Scores are heuristic prioritization, not performance forecasts.");
relevance.getRange("A4:I4").values=[["Creator","Angle","Brand fit","Q4 potential","Gifting","Product focus","Occasion","Brand-fit notes","TikTok source"]];
const relevanceRows=data.videos.map(v=>[v.creator_name,v.primary_angle,v.brand_fit_score,v.q4_potential_score,v.gifting_relevance_score,v.product_focus,v.occasion,v.brand_fit_notes,v.canonical_url]);if(relevanceRows.length)relevance.getRange("A5").write(relevanceRows);tableStyle(relevance,`A4:I${4+Math.max(1,relevanceRows.length)}`,"A4:I4");scoreFormat(relevance.getRange("C5:E200"));relevance.getRange("A:B").format.columnWidth=24;relevance.getRange("C:E").format.columnWidth=14;relevance.getRange("F:H").format.columnWidth=35;relevance.getRange("I:I").format.columnWidth=55;

const briefs=sheets["Generated Briefs"];title(briefs,"Generated briefs","Drafts require brand and legal approval before publishing.");briefs.getRange("A4:F4").values=[["Brand","Product","Generated","Brief path","Source count","Status"]];briefs.getRange("A5:F5").values=[["CoBa's Daughter","Bath & Body Care Gift Set",data.generated_at,"exports/briefs/",Math.min(3,data.videos.length),"Draft"]];tableStyle(briefs,"A4:F5","A4:F4");briefs.getRange("A:A").format.columnWidth=24;briefs.getRange("B:B").format.columnWidth=36;briefs.getRange("C:C").format.columnWidth=22;briefs.getRange("D:D").format.columnWidth=28;briefs.getRange("E:F").format.columnWidth=16;
briefs.getRange("C5").setNumberFormat("yyyy-mm-dd hh:mm");

const quality=sheets["Data Quality"];title(quality,"Data quality","Evidence gaps are kept visible and reduce confidence.");
quality.getRange("A4:C4").values=[["Check","Count","Action"]];const checks=[["Fixture records",data.videos.filter(v=>v.is_fixture).length,"Do not use fixture rows as live evidence"],["Missing views",data.videos.filter(v=>v.views==null).length,"Collect a view snapshot when accessible"],["Unverified country",data.videos.filter(v=>v.creator_country==="Unverified").length,"Add profile or third-party location evidence"],["Medium or low evidence",data.videos.filter(v=>["medium","low"].includes(v.evidence_quality)).length,"Re-verify before paid activation"]];quality.getRange("A5").write(checks);tableStyle(quality,"A4:C8","A4:C4");quality.getRange("A:C").format.autofitColumns();quality.getRange("C:C").format.columnWidth=48;

const run=sheets["Run Log"];title(run,"Run log","Current export metadata and score definition.");
run.getRange("A4:B4").values=[["Field","Value"]];run.getRange("A5:B10").values=[["Generated at",data.generated_at],["Video count",data.videos.length],["Fixture only",data.is_fixture_only],["Opportunity formula","25% momentum + 30% brand fit + 25% Q4 potential + 15% gifting relevance + 5% evidence"],["Brand source","CoBa's Daughter Brand Book"],["Strategy source","CoBa's Daughter Q4 Brand Plan"]];tableStyle(run,"A4:B10","A4:B4");run.getRange("A:A").format.columnWidth=24;run.getRange("B:B").format.columnWidth=105;run.getRange("B:B").format.wrapText=true;
run.getRange("B5").setNumberFormat("yyyy-mm-dd hh:mm");

for(const sheet of Object.values(sheets)){sheet.getUsedRange()?.format.autofitRows();}
await fs.mkdir(new URL(".",`file://${outputPath}`).pathname,{recursive:true}).catch(()=>{});
const blob=await SpreadsheetFile.exportXlsx(wb);await blob.save(outputPath);
const inspection=await wb.inspect({kind:"table",sheetId:"Top Videos",range:"A1:O12",include:"values,formulas",tableMaxRows:12,tableMaxCols:15});console.log(inspection.ndjson);
const errors=await wb.inspect({kind:"match",searchTerm:"#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A|#NUM!|#NULL!|#SPILL!|#CALC!",options:{useRegex:true,maxResults:100},summary:"final formula error scan"});console.log(errors.ndjson);
await fs.mkdir("work/workbook-sheets",{recursive:true});
for(const name of names){const rendered=await wb.render({sheetName:name,autoCrop:"all",scale:1});await fs.writeFile(`work/workbook-sheets/${name.toLowerCase().replaceAll(" ","-")}.png`,new Uint8Array(await rendered.arrayBuffer()));}
