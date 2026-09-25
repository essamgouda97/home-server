'use strict';
// Apply before styles paint. Dark is the default; a deliberate choice persists.
try{document.documentElement.dataset.theme=localStorage.getItem('workspace-theme')==='light'?'light':'dark'}catch{document.documentElement.dataset.theme='dark'}
