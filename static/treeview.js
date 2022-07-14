

function toggleCurveSimplify() {
	var el = $('#tree-button-div span:first-child'); 
	el.text(el.text() + "x");

	$('#treeholder svg path').each(function(){
	var dv = $( this ).attr("d");
	var adv =  $( this ).attr("alt_d");
	if (adv) {
		$( this ).attr("d", adv);
		$( this ).attr("alt_d", dv);
	}

 });
}

$(document).ready(function() {
	
})
;