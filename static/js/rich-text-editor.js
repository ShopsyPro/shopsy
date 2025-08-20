/**
 * Rich Text Editor Module
 * Provides rich text editing functionality with formatting options
 */
class RichTextEditor {
  constructor(options = {}) {
    this.editorId = options.editorId || 'richTextEditor';
    this.hiddenInputId = options.hiddenInputId || 'productDescription';
    this.toolbarClass = options.toolbarClass || 'rich-text-btn';
    this.isEdit = options.isEdit || false;
    
    this.editor = null;
    this.hiddenInput = null;
    
    this.init();
  }
  
  init() {
    this.editor = document.getElementById(this.editorId);
    this.hiddenInput = document.getElementById(this.hiddenInputId);
    
    if (!this.editor || !this.hiddenInput) {
      console.error('Rich text editor elements not found');
      return;
    }
    
    this.setupToolbar();
    this.setupEditor();
  }
  
  setupToolbar() {
    const toolbarButtons = document.querySelectorAll(`.${this.toolbarClass}`);
    
    toolbarButtons.forEach(button => {
      button.addEventListener('click', (e) => {
        e.preventDefault();
        this.execCommand(button.getAttribute('data-command'), button.getAttribute('data-value'));
      });
    });
  }
  
  setupEditor() {
    // Focus management
    this.editor.addEventListener('focus', () => {
      this.editor.classList.add('ring-2', 'ring-blue-500');
    });
    
    this.editor.addEventListener('blur', () => {
      this.editor.classList.remove('ring-2', 'ring-blue-500');
    });
    
    // Auto-update hidden input
    this.editor.addEventListener('input', () => {
      this.updateHiddenInput();
    });
    
    // Handle paste to clean HTML
    this.editor.addEventListener('paste', (e) => {
      e.preventDefault();
      const text = (e.originalEvent || e).clipboardData.getData('text/plain');
      document.execCommand('insertText', false, text);
    });
  }
  
  execCommand(command, value = null) {
    document.execCommand(command, false, value);
    this.editor.focus();
    this.updateHiddenInput();
  }
  
  updateHiddenInput() {
    if (this.hiddenInput) {
      this.hiddenInput.value = this.editor.innerHTML;
    }
  }
  
  setContent(content) {
    if (this.editor) {
      this.editor.innerHTML = content || '';
      this.updateHiddenInput();
    }
  }
  
  getContent() {
    return this.editor ? this.editor.innerHTML : '';
  }
  
  clear() {
    this.setContent('');
  }
}

// Export for use in other modules
if (typeof module !== 'undefined' && module.exports) {
  module.exports = RichTextEditor;
} else {
  window.RichTextEditor = RichTextEditor;
} 