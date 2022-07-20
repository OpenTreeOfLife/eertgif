

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

function handleClickOnGraph(evt) {
	var target = evt.target;
	var curve_id_str = "null";
	if (target.hasAttribute("curve_id")) {
		curve_id_str = target.getAttribute("curve_id");
	}
	var pref = "Clicked";
	if (evt.getModifierState("Control")) {
		pref = "Control-clicked"
	}
	console.log(pref + " on " + target.tagName + " id = " + target.getAttribute("id") + " curve_id = ", curve_id_str);
}

function detectComponents() {
	var val = $('#node_tol_input').val();
	var valf = Number(val);
	if (val === "" || isNaN(valf)) {
		alert("node tolerance for component detection must be a number");
		return;
	}
	var rval = $('#rect_axis_merge_tol').val();
	var rvalf = Number(rval);
	if (rval === "" || isNaN(rvalf)) {
		alert("Rect axis merge tol must be a number");
		return;
	}
	// var paramList = getSearchParamList();
	// paramList = insertParam("action", "detect_components", paramList);
	// paramList = insertParam("node_merge_tol", valf, paramList);
	// reloadPageWithParamList(paramList);	
	extract_config.node_merge_tol = valf
	extract_config.rect_base_intercept_tol = rvalf
	extract_config.viz_highlight_mode = $('#highlight_mode').val();
	data = {"action":"detect_components",
			"config": JSON.stringify(extract_config),
		}
	$.ajax({
    type: "POST",
    url: document.location,
    data: data,
    success: function() {   
        location.reload();  
    }
});
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
	extract_config.is_rect_shape = (dw > rw);
}

function textHiding(checkbx) {
	if (checkbx.checked) {
		$( "#treeholder svg text" ).each(function() {
			$( this ).attr("display", "none")
		});
		extract_config.viz_hide_text = true;
	} else {
		$( "#treeholder svg text" ).each(function() {
			$( this ).attr("display", "yes")
		});
		extract_config.viz_hide_text = false;
	}
}

function nodeHiding(checkbx) {
	if (checkbx.checked) {
		$( "#treeholder svg circle" ).each(function() {
			$( this ).attr("display", "none")
		});
		extract_config.viz_hide_nodes = true;
	} else {
		$( "#treeholder svg circle" ).each(function() {
			$( this ).attr("display", "yes")
		});
		extract_config.viz_hide_nodes = false;
	}
}

function edgeHiding(checkbx) {
	if (checkbx.checked) {
		$( "#treeholder svg path" ).each(function() {
			$( this ).attr("display", "none")
		});
		extract_config.viz_hide_edges = true;
	} else {
		$( "#treeholder svg path" ).each(function() {
			$( this ).attr("display", "yes")
		});
		extract_config.viz_hide_edges = false;
	}
}

function toggleCurveSimplify(target) {
	if (target.checked) {
		extract_config.viz_simplify_curves = true;
	} else {
		extract_config.viz_simplify_curves = false;
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
	 if (extract_config.orientation == "right") {
	 	extract_config.orientation = "down";
	 } else if (extract_config.orientation == "down") {
	 	extract_config.orientation = "left";
	 } else if (extract_config.orientation == "left") {
	 	extract_config.orientation = "up";
	 } else  {
	 	extract_config.orientation = "right";
	 }
}


function set_ui_based_on_config(){
	var rect_el = $('#rect_tree_shape_icon');
	if (rect_el.length) {
		var is_rect = extract_config.is_rect_shape;
		toggleTreeShape();
		if (is_rect != extract_config.is_rect_shape) {
			toggleTreeShape();
		}
		while (extract_config.orientation != "right") {
			rotateOrientationClicked();
		}
	}
	var he_chkbz = $( '#hide_edges_btn' );
	if (he_chkbz.length) {
		he_chkbz.prop('checked', extract_config.viz_hide_edges).trigger("change");
	}
	var hn_chkbz = $( '#hide_nodes_btn' );
	if (hn_chkbz.length) {
		hn_chkbz.prop('checked', extract_config.viz_hide_nodes).trigger("change");
	}
	var ht_chkbz = $( '#hide_text_btn' );
	if (ht_chkbz.length) {
		ht_chkbz.prop('checked', extract_config.viz_hide_text).trigger("change");
	}
	if (!extract_config.viz_simplify_curves) {
		$( '#simplify_paths_btn' ).prop('checked', false).trigger("change");
	}
	$( "#highlight_mode").val(extract_config.viz_highlight_mode).trigger("change");
	// var cb_stat = .is(":checked");
	// if (cb_stat != viz_hide_edges) {
	// 	edgeHiding
	// }
	
}

/////////////////////////////////////////////////////
// svg-drag-select code:
function strictIntersectionSelector(context) {
  const dragAreaInSvgCoordinate = context.dragAreaInSvgCoordinate
  return context.getIntersections().filter(function (element) {
    if (context.pointerEvent.target === element) {
      return true
    }
    if (!(element instanceof SVGPathElement)) {
      // strictly check only <path>s.
      return true
    }
    for (let i = 0, len = element.getTotalLength(); i <= len; i += 4 /* arbitrary */) {
      const point = element.getPointAtLength(i)
      const x = point.x
      const y = point.y
      if (
          dragAreaInSvgCoordinate.x <= x && x <= dragAreaInSvgCoordinate.x + dragAreaInSvgCoordinate.width &&
          dragAreaInSvgCoordinate.y <= y && y <= dragAreaInSvgCoordinate.y + dragAreaInSvgCoordinate.height
      ) {
        return true
      }
    }
    return false
  })
}

var svgDragSelectOptions = {
  svg: document.getElementsByTagName('svg')[0],
  // onSelectionStart: function (selectionStart) {
  //   console.log("onSelectionStart", selectionStart)
  //   const selectedElements = selectionStart.svg.querySelectorAll('[data-selected]')
  //   for (let i = 0; i < selectedElements.length; i++) {
  //     selectedElements[i].removeAttribute('data-selected')
  //   }
  //   document.getElementById('selected-items').value = ''
  // },
  // onSelectionEnd: function (selectionEnd) {
  //   console.log("onSelectionEnd", selectionEnd)
  // },
  // onSelectionChange: function (selectionChange) {
  //   console.log("onSelectionChange", selectionChange)
  //   selectionChange.newlyDeselectedElements.forEach(function (element) {
  //     element.removeAttribute('data-selected')
  //   })
  //   selectionChange.newlySelectedElements.forEach(function (element) {
  //     element.setAttribute('data-selected', '')
  //   })
  //   document.getElementById('selected-items').value = selectionChange.selectedElements
  //     .map(function (element) { return element.getAttribute('data-name') })
  //     .sort()
  //     .join('\n')
  // },
  // selector: strictIntersectionSelector
}


$(document).ready(function() {
	if (extract_config !== null) {
		set_ui_based_on_config();
	}
	$("circle").each(add_to_map);
	$("path").each(add_to_map);

	window.svgDragSelect(svgDragSelectOptions);
//	window.svgDragSelectOptions.svg.style.visibility = 'visible';
})
;