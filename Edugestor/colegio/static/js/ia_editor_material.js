/* Progressive enhancement: the server still receives the existing text fields. */
(() => {
    'use strict';
    const root = document.querySelector('[data-editor-material]');
    if (!root || !window.TurndownService || !window.turndownPluginGfm) return;

    const form = root.closest('form');
    const converter = new window.TurndownService({ headingStyle: 'atx', bulletListMarker: '-', emDelimiter: '*' });
    converter.use(window.turndownPluginGfm.tables);
    converter.addRule('apoyoVisual', {
        filter: node => node.nodeName === 'FIGURE' && /^[1-6]$/.test(node.dataset.recursoId || ''),
        replacement: (_, node) => `\n\n[[visual:${node.dataset.recursoId}]]\n\n`
    });
    const sections = [...root.querySelectorAll('[data-editor-seccion]')].map(panel => {
        const editor = panel.querySelector('[data-editor-campo]');
        const source = panel.querySelector('textarea');
        return { panel, editor, source, initialHTML: editor.innerHTML, initialSource: source.value };
    });
    const tabs = [...root.querySelectorAll('[role=tab]')];
    const toolbar = root.querySelector('.ia-editor-toolbar');
    const style = root.querySelector('#editor-formato');
    const status = form.querySelector('[data-editor-estado]');
    const error = root.querySelector('[data-editor-error]');
    let active = sections[0];
    let savedRange = null;
    let submitting = false;
    let dirty = false;

    function pending() {
        dirty = true;
        status.textContent = 'Tienes cambios sin guardar';
        status.dataset.pendiente = 'true';
    }

    function wordCount() {
        const text = active.editor.innerText.trim();
        const count = text ? text.split(/\s+/u).length : 0;
        root.querySelector('[data-editor-palabras]').textContent = `${count} ${count === 1 ? 'palabra' : 'palabras'}`;
    }

    function selectSection(name, focusTab = false) {
        active = sections.find(section => section.source.name === name) || sections[0];
        savedRange = null;
        for (const section of sections) section.panel.hidden = section !== active;
        for (const tab of tabs) {
            const selected = tab.dataset.seccion === active.source.name;
            tab.setAttribute('aria-selected', String(selected));
            tab.tabIndex = selected ? 0 : -1;
            if (selected && focusTab) tab.focus();
        }
        wordCount();
        toolbarState();
    }

    function rememberSelection() {
        const selection = window.getSelection();
        if (selection.rangeCount && active.editor.contains(selection.anchorNode) && active.editor.contains(selection.focusNode)) {
            savedRange = selection.getRangeAt(0).cloneRange();
            return true;
        }
        return false;
    }

    function restoreSelection() {
        active.editor.focus();
        const selection = window.getSelection();
        selection.removeAllRanges();
        if (savedRange && active.editor.contains(savedRange.commonAncestorContainer)) {
            selection.addRange(savedRange);
        } else {
            const range = document.createRange();
            range.selectNodeContents(active.editor);
            range.collapse(false);
            selection.addRange(range);
        }
    }

    function toolbarState() {
        for (const button of toolbar.querySelectorAll('[aria-pressed]')) {
            button.setAttribute('aria-pressed', String(Boolean(savedRange) && document.queryCommandState(button.dataset.comando)));
        }
        const selection = window.getSelection();
        let node = selection.anchorNode;
        if (node?.nodeType === Node.TEXT_NODE) node = node.parentElement;
        const heading = node?.closest?.('h1,h2,h3,h4');
        const tag = heading && active.editor.contains(heading) ? heading.tagName.toLowerCase() : 'p';
        // Generated main headings remain unchanged unless the teacher chooses a style.
        style.value = ['h2', 'h3'].includes(tag) ? tag : 'p';
    }

    function execute(command, value = null) {
        restoreSelection();
        // Native editing commands retain the browser's undo history. Avoid DOM rewrites
        // while typing so caret position, input methods and undo remain native.
        document.execCommand(command, false, value);
        rememberSelection();
        toolbarState();
    }

    function syncSources() {
        for (const section of sections) {
            section.source.value = section.editor.innerHTML === section.initialHTML
                ? section.initialSource : converter.turndown(section.editor);
        }
    }

    for (const section of sections) {
        section.panel.setAttribute('role', 'tabpanel');
        section.panel.setAttribute('aria-labelledby', `tab-${section.source.name}`);
        section.editor.contentEditable = 'true';
        section.editor.hidden = false;
        section.panel.querySelector('.ia-editor-seccion-cabecera').hidden = false;
        section.panel.querySelector('[data-editor-respaldo]').hidden = true;
        section.source.required = false;
        section.editor.addEventListener('input', () => {
            error.hidden = true;
            pending();
            wordCount();
            rememberSelection();
        });
        section.editor.addEventListener('paste', event => {
            if (!event.clipboardData) return;
            event.preventDefault();
            // Paste text, never executable clipboard HTML or Word's inline styles.
            rememberSelection();
            execute('insertText', event.clipboardData.getData('text/plain'));
        });
        section.editor.addEventListener('drop', event => event.preventDefault());
    }
    for (const tab of tabs) tab.addEventListener('click', () => selectSection(tab.dataset.seccion));
    root.querySelector('[role=tablist]').addEventListener('keydown', event => {
        const index = tabs.indexOf(document.activeElement);
        if (index < 0) return;
        let next;
        if (event.key === 'ArrowRight') next = (index + 1) % tabs.length;
        if (event.key === 'ArrowLeft') next = (index + tabs.length - 1) % tabs.length;
        if (event.key === 'Home') next = 0;
        if (event.key === 'End') next = tabs.length - 1;
        if (next !== undefined) { event.preventDefault(); selectSection(tabs[next].dataset.seccion, true); }
    });
    document.addEventListener('selectionchange', () => {
        if (rememberSelection()) toolbarState();
    });
    toolbar.addEventListener('mousedown', event => {
        if (event.target.closest('button')) event.preventDefault();
    });
    toolbar.addEventListener('click', event => {
        const button = event.target.closest('[data-comando]');
        if (button) execute(button.dataset.comando);
    });
    style.addEventListener('change', () => execute('formatBlock', style.value));

    const dialog = root.querySelector('dialog');
    const nuevoVisual = form.querySelector('[data-nuevo-visual]');
    if (nuevoVisual) {
        const tipo = nuevoVisual.querySelector('[name=nuevo_visual_tipo]');
        const opciones = {
            ajuste: ['Primer número', 'Segundo número', 48, 35],
            posicional: ['Primer número', 'Segundo número', 456, 237],
            recta: ['Primer número', 'Segundo número (suma hasta 30)', 27, 8],
            grupos: ['Filas (1 a 6)', 'Puntos por fila (1 a 10)', 3, 4],
            reparto: ['Total de elementos (hasta 60)', 'Grupos (1 a 6, sin resto)', 24, 4],
            fraccion: ['Partes coloreadas', 'Total de partes (2 a 12)', 3, 4]
        };
        tipo.addEventListener('change', () => {
            const [a,b,va,vb] = opciones[tipo.value];
            nuevoVisual.querySelector('[data-etiqueta-a]').textContent = a;
            nuevoVisual.querySelector('[data-etiqueta-b]').textContent = b;
            nuevoVisual.querySelector('[name=nuevo_visual_a]').value = va;
            nuevoVisual.querySelector('[name=nuevo_visual_b]').value = vb;
            nuevoVisual.querySelector('[data-nueva-operacion]').hidden = !['ajuste','posicional','recta'].includes(tipo.value);
            nuevoVisual.querySelector('[data-operacion-multiplicar]').hidden = tipo.value !== 'posicional';
            nuevoVisual.querySelector('[name=nuevo_visual_operacion]').value = '+';
        });
    }
    const preview = root.querySelector('[data-editor-preview-documento]');
    root.querySelector('[data-editor-preview]').addEventListener('click', () => {
        preview.replaceChildren();
        const title = document.createElement('h1');
        title.textContent = form.querySelector('[name=titulo]').value;
        preview.append(title);
        for (const section of sections.filter(item => item.source.name !== 'solucionario')) {
            if (!section.editor.innerText.trim()) continue;
            if (section.source.name === 'ejercicios') {
                const heading = document.createElement('h2');
                heading.textContent = 'Ejercicios propuestos';
                preview.append(heading);
            }
            const copy = section.editor.cloneNode(true);
            copy.removeAttribute('id');
            copy.removeAttribute('contenteditable');
            copy.removeAttribute('role');
            copy.removeAttribute('aria-labelledby');
            copy.removeAttribute('aria-describedby');
            copy.removeAttribute('data-editor-campo');
            copy.className = '';
            preview.append(copy);
        }
        dialog.showModal();
    });
    root.querySelector('[data-editor-cerrar-preview]').addEventListener('click', () => dialog.close());
    form.addEventListener('input', event => {
        if (!root.contains(event.target)) pending();
    });
    form.addEventListener('submit', event => {
        syncSources();
        if (!sections[0].editor.innerText.trim()) {
            event.preventDefault();
            event.stopImmediatePropagation();
            selectSection('contenido');
            error.textContent = 'Escribe una explicación antes de guardar el material.';
            error.hidden = false;
            active.editor.focus();
            return;
        }
        submitting = true;
    }, true);
    window.addEventListener('beforeunload', event => {
        if (dirty && !submitting) { event.preventDefault(); event.returnValue = ''; }
    });
    window.addEventListener('pageshow', () => { submitting = false; });
    root.querySelector('.ia-editor-navegacion').hidden = false;
    toolbar.hidden = false;
    root.querySelector('.ia-editor-pie').hidden = false;
    selectSection('contenido');
    root.dataset.editorListo = 'true';
})();
