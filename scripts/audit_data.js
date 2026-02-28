const https = require("https");
const fs = require("fs");
const BASE = "https://brain-mri-7bp6oqdu7a-uc.a.run.app/api/v1";

function fetchJSON(url) {
  return new Promise((resolve, reject) => {
    https.get(url, { timeout: 30000 }, (res) => {
      let data = "";
      res.on("data", c => data += c);
      res.on("end", () => {
        try { resolve(JSON.parse(data)); }
        catch(e) { reject(new Error("Parse: " + data.substring(0,200))); }
      });
    }).on("error", reject);
  });
}

function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }

async function main() {
  console.log("=== ISBI-MS DATA AUDIT ===");
  var pResp = await fetchJSON(BASE + "/patients?limit=50");
  var patients = pResp.items || pResp;
  console.log("Total patients: " + patients.length);
  patients.sort((a,b) => (a.mrn||"").localeCompare(b.mrn||""));
  var allM = [], allMasks = [], sums = [];
  for (var p of patients) {
    var mrn = p.mrn || "";
    if (!mrn.startsWith("ISBI-MS-")) continue;
    console.log("");
    console.log("PATIENT: " + mrn);
    await sleep(200);
    var sr = await fetchJSON(BASE+"/studies?patient_id="+p.id+"&limit=50");
    var sts = sr.items || sr;
    if (!Array.isArray(sts)) continue;
    sts.sort((a,b) => (a.study_date||a.created_at||"").localeCompare(b.study_date||b.created_at||""));
    console.log("  Studies: " + sts.length);
    var pM=[], pMk=[];
    for (var si=0; si<sts.length; si++) {
      var st=sts[si], tp=si+1, sd=st.study_date||st.created_at||"N/A";
      console.log("  TP"+tp+": "+st.id+" Date:"+sd);
      await sleep(200);
      var serR = await fetchJSON(BASE+"/studies/"+st.id+"/series");
      var sers = serR.items || serR;
      if (!Array.isArray(sers)) continue;
      for (var ser of sers) {
        await sleep(150);
        var iR = await fetchJSON(BASE+"/studies/series/"+ser.id+"/instances");
        var insts = iR.items || iR;
        if (!Array.isArray(insts)) continue;
        if (insts.length>0) console.log("    Ser#"+(ser.series_number||"?")+"("+( ser.series_description||ser.description||"")+"): "+insts.length+" inst");
        for (var inst of insts) {
          var fn=inst.original_filename||inst.filename||"";
          var gcs=inst.gcs_object_name||inst.gcs_path||"";
          var iid=inst.id||"";
          var mask=/_dseg\.|label-lesion|expert|out_mask|mask/i.test(fn);
          if(mask) pMk.push({iid:iid,sid:st.id,tp:tp,fn:fn,gcs:gcs,mrn:mrn,snum:ser.series_number,serid:ser.id});
          var sm=fn.match(/ses-(\d+)/);
          if(sm){var sn=parseInt(sm[1],10); if(sn!==tp){
            pM.push({mrn:mrn,iid:iid,serid:ser.id,snum:ser.series_number,sid:st.id,ctp:tp,ses:sn,fn:fn,gcs:gcs,mask:mask,sd:sd});
            console.log("      ***MISPLACED: "+fn+" in TP"+tp+" should be TP"+sn);
          }}
          console.log("      "+fn);
        }
      }
    }
    sums.push({mrn:mrn,ns:sts.length,nm:pM.length,nmk:pMk.length});
    allM=allM.concat(pM); allMasks=allMasks.concat(pMk);
    if(pM.length>0)console.log("  >>>"+mrn+": "+pM.length+" MISPLACED<<<");
    else console.log("  "+mrn+": OK");
  }
  console.log("");
  console.log("########## SUMMARY ##########");
  console.log("MRN              |Stud|Mask|Mispl");
  for(var s of sums) console.log(s.mrn.padEnd(17)+"|"+String(s.ns).padStart(4)+"|"+String(s.nmk).padStart(4)+"|"+String(s.nm).padStart(5));
  console.log("TOTAL: "+sums.length+" patients, "+allM.length+" misplaced, "+allMasks.length+" masks");
  if(allMasks.length>0){console.log(""); console.log("MASK FILES:"); for(var m of allMasks) console.log(" "+m.mrn+" TP"+m.tp+" | "+m.fn+" | "+m.iid+" | "+m.gcs);}
  if(allM.length>0){
    console.log(""); console.log("MISPLACED FILES:");
    for(var m of allM){console.log(" "+m.mrn+" | "+m.fn); console.log("   CurrTP"+m.ctp+" ShouldTP"+m.ses+" | "+m.iid+" | "+m.gcs+" | mask:"+m.mask);}
    var af=[]; allM.forEach(function(m){if(!af.includes(m.mrn))af.push(m.mrn)}); af.sort();
    console.log("AFFECTED("+af.length+"): "+af.join(", "));
  }else console.log(""); console.log("NO MISPLACED FILES");
  var rpt={date:new Date().toISOString(),patients:sums.length,misplaced:allM.length,masks:allMasks.length,sums:sums,allM:allM,allMasks:allMasks};
  fs.writeFileSync("c:/Users/Nicolas/medical-imaging-viewer/audit_report.json",JSON.stringify(rpt,null,2));
  console.log("Saved audit_report.json");
}
main().catch(function(e){console.error("FATAL:",e);process.exit(1);});
