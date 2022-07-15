

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

function setColorsForSameComp(comp_id, stroke_color, fill_color) {
	var el_of_same_comp = el_by_comp_id[comp_id]
	if (typeof el_of_same_comp === 'undefined') {
		return;
	}
	var i = 0;
	var el;
	for (; i < el_of_same_comp.length; i++) {
		el = el_of_same_comp[i];
		var nhf = el.getAttribute("nhfcolor");
		if (nhf !== "none") {
			if (fill_color === "none") {
				el.setAttribute("fill", nhf)
			} else {
				el.setAttribute("fill", fill_color);
			}
		}
		var nhs = el.getAttribute("nhscolor");
		if (nhs !== "none") {
			if (stroke_color === "none") {
				el.setAttribute("stroke", nhs)
			} else {
				el.setAttribute("stroke", stroke_color);
			}
		}
	}
}

function mouseOverNode(target) {
	var comp_id = target.getAttribute("component");
	if (typeof comp_id === 'undefined') {
		return;
	}
	setColorsForSameComp(comp_id, "red", "red");
	// var edge_refs = target.getAttribute("edges");
	// if (!edge_refs || edge_refs === "") {
	// 	return;
	// }
	// var edge_list = edge_refs.split(",")
	// var er;
	// let i=0
	// for (; i <edge_list.length; i++) {
	// 	er = "#" + edge_list[i].trim();
	// 	$( er ).attr("stroke", "red");
	// }
}

var mouseOverEdge = mouseOverNode;

function mouseOutNode(target) {
	var comp_id = target.getAttribute("component");
	if (typeof comp_id === 'undefined') {
		return;
	}
	setColorsForSameComp(comp_id, target.getAttribute("nhscolor"), target.getAttribute("nhfcolor"));
}

var mouseOutEdge = mouseOutNode;

function detectComponents() {
	var val = $('#node_tol_input').val();
	var valf = Number(val);
	if (val === "" || isNaN(valf)) {
		alert("node tolerance for component detection must be a number");
		return;
	}
	var paramList = getSearchParamList();
	paramList = insertParam("action", "detect_components", paramList);
	paramList = insertParam("node_merge_tol", valf, paramList);
	reloadPageWithParamList(paramList);	
}

var el_by_comp_id = {};
function add_to_map() {
	var comp_id = $( this ).attr("component");
	if (typeof comp_id === 'undefined') {
		return;
	}
	var x = el_by_comp_id[comp_id];
	if (x === undefined) {
		el_by_comp_id[comp_id] = [this];
	} else {
		x[x.length] = this;
	}
}

$(document).ready(function() {

	$("circle").each(add_to_map);
	$("path").each(add_to_map);
})
;