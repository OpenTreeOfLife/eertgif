

var el_by_comp_id = {};


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
	if ( $( "#path_desc" ).text() == "simplified") {
		$( "#path_desc" ).text("connected points");
		$( "#simplify_btn_text" ).text("Simplify");
	} else {
		$( "#path_desc" ).text("simplified");
		$( "#simplify_btn_text" ).text("Connect points");	
	}
	$('#treeholder svg path').each(function(){
	var dv = $( this ).attr("d");
	var adv =  $( this ).attr("alt_d");
	if (adv) {
		$( this ).attr("d", adv);
		$( this ).attr("alt_d", dv);
	}
 });
}


function colorElIfNHColorNonNone(el, stroke_color, fill_color) {
	el.setAttribute("display", "yes");
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

function setColorsForSameComp(comp_id, stroke_color, fill_color, nonmatching_display) {
	var el_of_same_comp = el_by_comp_id[comp_id]
	if (typeof el_of_same_comp === 'undefined') {
		return;
	}
	setDisplayForGraph(nonmatching_display);
	var i = 0;
	var el;
	for (; i < el_of_same_comp.length; i++) {
		el = el_of_same_comp[i];
		colorElIfNHColorNonNone(el, stroke_color, fill_color);
	}
}

function colorComSepList(edge_refs, stroke_color, fill_color) {
	var er;
	var el;
	if (edge_refs && edge_refs !== "") {
		var edge_list = edge_refs.split(",")
		let i=0
		for (; i < edge_list.length; i++) {
			er = "#" + edge_list[i].trim();
			el = $( er ).get(0);
			colorElIfNHColorNonNone(el, stroke_color, fill_color);
		}
	}
}
function setDisplayForGraph(nonmatching_display) {
	$("#treeholder svg path").each(function() {
		$( this ).attr("display", nonmatching_display);
	});
	$("#treeholder svg circle").each(function() {
		$( this ).attr("display", nonmatching_display);
	});
}

function setColorsForNeighbors(el, stroke_color, fill_color, nonmatching_display) {
	setDisplayForGraph(nonmatching_display);
	colorComSepList(el.getAttribute("edges"), stroke_color, fill_color);
	colorComSepList(el.getAttribute("nodes"), stroke_color, fill_color);
}


function mouseColorEvent(target, sc, fc, out_move) {
	var nonmatching_display;
	var highlight_mode = $("#highlight_mode").val();
	if (highlight_mode == "component" || highlight_mode == "component-only") {
		var comp_id = target.getAttribute("component");
		if (typeof comp_id === 'undefined') {
			return;
		}
		if (out_move || highlight_mode == "component" ) {
			nonmatching_display = "yes";
		} else {
			nonmatching_display = "none"
		}
		setColorsForSameComp(comp_id, sc, fc, nonmatching_display);
	} else if (highlight_mode == "neighbors" || highlight_mode == "neighbors-only") {
		if (out_move || highlight_mode == "neighbors" ) {
			nonmatching_display = "yes";
		} else {
			nonmatching_display = "none"
		}
		setColorsForNeighbors(target, sc, fc, nonmatching_display);
	}
	colorElIfNHColorNonNone(target, sc, fc);
	
}
function mouseOverNode(target) {
	var sc = "red";
	var fc = "red";
	mouseColorEvent(target, sc, fc, false);
}

var mouseOverEdge = mouseOverNode;

function mouseOutNode(target) {
	var sc = target.getAttribute("nhscolor");
	var fc = target.getAttribute("nhfcolor");
	mouseColorEvent(target, sc, fc, true);
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

function toggleTreeShape() {
	var rw = $('#rect_tree_shape_icon').attr("width");
	var dw= $('#diag_tree_shape_icon').attr("width");
	var rwn = Number(rw);
	var dwn= Number(dw);
	$('#rect_tree_shape_icon').attr("width", dw);
	$('#diag_tree_shape_icon').attr("width", rw);
	vis_style.is_rect_shape = rw > dw;
}

function textHiding(checkbx) {
	if (checkbx.checked) {
		$( "#treeholder svg text" ).each(function() {
			$( this ).attr("display", "none")
		});
	} else {
		$( "#treeholder svg text" ).each(function() {
			$( this ).attr("display", "yes")
		});
	}
}

// modified from https://stackoverflow.com/questions/20061774/rotate-an-image-in-image-source-in-html
function rotate_img_90cw(obj) {
    var deg = obj.data('rotate') || 0;
    deg += 90;
    if (deg >= 360) {
    	deg -= 360;
    }
    obj.data('rotate', deg);
    var rotate = 'rotate(' + deg +  'deg)';
    obj.css({ 
        '-webkit-transform': rotate,
        '-moz-transform': rotate,
        '-o-transform': rotate,
        '-ms-transform': rotate,
        'transform': rotate 
    });
}

function rotateOrientationClicked() {
	 rotate_img_90cw($('#rect_tree_shape_icon'));
	 rotate_img_90cw($('#diag_tree_shape_icon'));
	 if (vis_style.orientation == "right") {
	 	vis_style.orientation = "down";
	 } else if (vis_style.orientation == "down") {
	 	vis_style.orientation = "left";
	 } else if (vis_style.orientation == "left") {
	 	vis_style.orientation = "up";
	 } else  {
	 	vis_style.orientation = "right";
	 }
}

$(document).ready(function() {
	var rect_el = $('#rect_tree_shape_icon');
	if (rect_el.length) {
		var is_rect = vis_style.is_rect_shape;
		toggleTreeShape();
		if (is_rect != vis_style.is_rect_shape) {
			toggleTreeShape();
		}
		while (vis_style.orientation != "right") {
			rotateOrientationClicked();
		}
	}
	$("circle").each(add_to_map);
	$("path").each(add_to_map);
})
;