//go:build darwin

package main

// C->Go bridge for the macOS panel load-failure log (separate file per the cgo
// //export-vs-C-definitions rule; the ObjC lives in panels_loadfail_darwin.go).

import "C"

import "log"

//export goPanelLoadFailed
func goPanelLoadFailed(panelID, failingURL, domain *C.char, code C.long, desc *C.char) {
	log.Print(panelLoadFailureLine(C.GoString(panelID), C.GoString(failingURL),
		C.GoString(domain), int(code), C.GoString(desc)))
}
