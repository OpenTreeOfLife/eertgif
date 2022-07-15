

/////////////////////////////////////////////////////////////////
// following 3 functions modified from https://stackoverflow.com/posts/487049/revisions
function getSearchParamList() {
	return document.location.search.substr(1).split('&');
}

function insertParam(key, value, paramList) {
    key = encodeURIComponent(key);
    value = encodeURIComponent(value);

    // paramList looks like ['key1=value1', 'key2=value2', ...]
    let i=0;

    for(; i<paramList.length; i++){
        if (paramList[i].startsWith(key + '=')) {
            let pair = paramList[i].split('=');
            pair[1] = value;
            paramList[i] = pair.join('=');
            break;
        }
    }

    if(i >= paramList.length){
        paramList[paramList.length] = [key,value].join('=');
    }
    return paramList;
}

function reloadPageWithParamList(paramList) {
    // can return this or...
    let params = paramList.join('&');

    // reload page with new params
    document.location.search = params;
}
/////////////////////////////////////////////////////////////////

function toggleCurveSimplify() {
	$('#treeholder svg path').each(function(){
	var dv = $( this ).attr("d");
	var adv =  $( this ).attr("alt_d");
	if (adv) {
		$( this ).attr("d", adv);
		$( this ).attr("alt_d", dv);
	}
 });
}

function detectComponents() {
	var val = $('#node_tol_input').val();
	var valf = Number(val);
	if (isNaN(valf)) {
		alert("node tolerance for component detection must be a number");
		return;
	}
	var paramList = getSearchParamList();
	paramList = insertParam("action", "detect_components", paramList);
	paramList = insertParam("node_merge_tol", valf, paramList);
	reloadPageWithParamList(paramList);	
}

$(document).ready(function() {
	
})
;