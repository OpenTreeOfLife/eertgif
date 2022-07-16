

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
	var is_rect = vis_style.is_rect_shape:
	toggleTreeShape();
	while (is_rect != vis_style.is_rect_shape) {
		toggleTreeShape();
	}
	if (Number($('#rect_tree_shape_icon').attr("width")) > 0) {
		is_rect_shape = true;
	} else {
		is_rect_shape = false;
	}
	while (vis_style.orientation != "right") {
		rotateOrientationClicked();
	}
	$("circle").each(add_to_map);
	$("path").each(add_to_map);
})
;