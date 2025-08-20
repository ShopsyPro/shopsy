/**
 * Image Cropper Module
 * Provides image cropping functionality with device previews
 */
class ImageCropper {
  constructor(options = {}) {
    this.cropperId = options.cropperId || 'cropper';
    this.cropControlsId = options.cropControlsId || 'imageCropControls';
    this.cropPreviewId = options.cropPreviewId || 'cropPreview';
    this.fileInputId = options.fileInputId || 'productImage';
    this.isEdit = options.isEdit || false;
    
    this.cropper = null;
    this.originalImage = null;
    
    this.init();
  }
  
  init() {
    this.setupCropControls();
    this.setupDeviceTabs();
    this.setupAspectRatioButtons();
  }
  
  setupCropControls() {
    const cropControls = document.getElementById(this.cropControlsId);
    const cropPreview = document.getElementById(this.cropPreviewId);
    const cropRatioBtns = document.querySelectorAll(this.isEdit ? '.edit-crop-ratio-btn' : '.crop-ratio-btn');
    const cropResetBtn = document.getElementById(this.isEdit ? 'editCropResetBtn' : 'cropResetBtn');
    const cropRotateBtn = document.getElementById(this.isEdit ? 'editCropRotateBtn' : 'cropRotateBtn');
    const cropImageBtn = document.getElementById(this.isEdit ? 'editCropImageBtn' : 'cropImageBtn');
    
    // Aspect ratio buttons
    cropRatioBtns.forEach(btn => {
      btn.addEventListener('click', () => {
        cropRatioBtns.forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        
        if (this.cropper) {
          const ratio = btn.getAttribute('data-ratio');
          if (ratio === 'free') {
            this.cropper.setAspectRatio(NaN);
          } else {
            const [w, h] = ratio.split(':').map(Number);
            this.cropper.setAspectRatio(w / h);
          }
        }
      });
    });
    
    // Reset crop
    cropResetBtn.addEventListener('click', () => {
      if (this.cropper) {
        this.cropper.reset();
        // Restart real-time previews after reset
        setTimeout(() => {
          this.setupRealTimePreviews();
        }, 100);
      }
    });
    
    // Rotate image
    cropRotateBtn.addEventListener('click', () => {
      if (this.cropper) {
        this.cropper.rotate(90);
      }
    });
    
    // Apply crop
    cropImageBtn.addEventListener('click', () => {
      if (this.cropper) {
        const canvas = this.cropper.getCroppedCanvas();
        if (canvas) {
          // Stop real-time previews
          this.stopRealTimePreviews();
          
          // Convert canvas to blob and update file input
          canvas.toBlob((blob) => {
            const file = new File([blob], 'cropped-image.jpg', { type: 'image/jpeg' });
            const dataTransfer = new DataTransfer();
            dataTransfer.items.add(file);
            document.getElementById(this.fileInputId).files = dataTransfer.files;
            
            // Update preview
            this.showImagePreview(file);
            
            // Hide crop controls
            cropControls.classList.add('hidden');
            
            // Clean up cropper
            if (this.cropper) {
              this.cropper.destroy();
              this.cropper = null;
            }
          }, 'image/jpeg', 0.9);
        }
      }
    });
  }
  
  setupDeviceTabs() {
    const deviceTabs = document.querySelectorAll(this.isEdit ? '.edit-device-tab' : '.device-tab');
    const devicePreviews = document.querySelectorAll(this.isEdit ? '.edit-device-preview' : '.device-preview');
    
    // Handle device tab switching
    deviceTabs.forEach(tab => {
      tab.addEventListener('click', () => {
        const device = tab.getAttribute('data-device');
        
        // Update active tab
        deviceTabs.forEach(t => {
          t.classList.remove('active', 'bg-blue-600', 'text-white');
          t.classList.add('bg-gray-700', 'text-gray-300');
        });
        tab.classList.add('active', 'bg-blue-600', 'text-white');
        tab.classList.remove('bg-gray-700', 'text-gray-300');
        
                 // Show corresponding preview
         devicePreviews.forEach(preview => {
           preview.classList.add('hidden');
           preview.classList.remove('active');
         });
         
         // Handle different ID patterns for add vs edit
         let previewId;
         if (this.isEdit) {
           previewId = 'edit' + device.charAt(0).toUpperCase() + device.slice(1) + 'Preview';
         } else {
           previewId = device + 'Preview';
         }
         
         const previewElement = document.getElementById(previewId);
         if (previewElement) {
           previewElement.classList.remove('hidden');
           previewElement.classList.add('active');
         }
      });
    });
  }
  
  setupAspectRatioButtons() {
    // This is handled in setupCropControls for better organization
  }
  
  resetCropInterface() {
    if (this.cropper) {
      this.cropper.destroy();
      this.cropper = null;
    }
    
    const cropControls = document.getElementById(this.cropControlsId);
    if (cropControls) {
      cropControls.classList.add('hidden');
    }
    
    const cropPreview = document.getElementById(this.cropPreviewId);
    if (cropPreview) {
      cropPreview.innerHTML = '<span class="text-gray-500 text-sm">Upload an image to start cropping</span>';
    }
    
    console.log('Crop interface reset - new image selected');
  }
  
  showCropInterface(imageUrl, file) {
    const cropControls = document.getElementById(this.cropControlsId);
    const cropPreview = document.getElementById(this.cropPreviewId);
    
    // Check if Cropper.js is loaded
    if (typeof Cropper === 'undefined') {
      console.error('Cropper.js library not loaded');
      alert('Image cropping library not loaded. Please refresh the page and try again.');
      return;
    }
    
    // Clean up existing cropper first
    if (this.cropper) {
      this.cropper.destroy();
      this.cropper = null;
    }
    
    // Clear the preview container
    cropPreview.innerHTML = '';
    
    // Show crop controls
    cropControls.classList.remove('hidden');
    
    // Create image for cropping
    const img = new Image();
    img.crossOrigin = 'anonymous'; // Handle CORS issues
    
    img.onload = () => {
      // Clear and add the new image
      cropPreview.innerHTML = '';
      cropPreview.appendChild(img);
      
      // Small delay to ensure DOM is ready
      setTimeout(() => {
        try {
          this.cropper = new Cropper(img, {
            aspectRatio: 1,
            viewMode: 1,
            dragMode: 'move',
            autoCropArea: 1,
            restore: false,
            guides: true,
            center: true,
            highlight: false,
            cropBoxMovable: true,
            cropBoxResizable: true,
            toggleDragModeOnDblclick: false,
          });
          
          // Set up real-time preview updates
          this.setupRealTimePreviews();
          
        } catch (error) {
          console.error('Error initializing cropper:', error);
          alert('Error initializing image cropper. Please try again.');
        }
      }, 100);
    };
    
    img.onerror = () => {
      console.error('Error loading image for cropping');
      alert('Error loading image for cropping. Please try again.');
    };
    
    img.src = imageUrl;
  }
  
  updateDevicePreviews() {
    if (!this.cropper) return;
    
    try {
      // Get the cropped canvas
      const canvas = this.cropper.getCroppedCanvas();
      if (!canvas) return;
      
             // Update desktop preview (3-column grid - shorter height)
       let desktopPreviewId;
       if (this.isEdit) {
         desktopPreviewId = 'editCropPreviewDesktop';
       } else {
         desktopPreviewId = 'cropPreviewDesktop';
       }
       const desktopPreview = document.getElementById(desktopPreviewId);
       if (desktopPreview) {
         const desktopCanvas = this.cropper.getCroppedCanvas({
           width: 300,
           height: 120,
           imageSmoothingEnabled: true,
           imageSmoothingQuality: 'high'
         });
         desktopPreview.innerHTML = '';
         desktopCanvas.style.width = '100%';
         desktopCanvas.style.height = '100%';
         desktopCanvas.style.objectFit = 'cover';
         desktopPreview.appendChild(desktopCanvas);
       }
       
       // Update tablet preview (2-column grid - medium height)
       let tabletPreviewId;
       if (this.isEdit) {
         tabletPreviewId = 'editCropPreviewTablet';
       } else {
         tabletPreviewId = 'cropPreviewTablet';
       }
       const tabletPreview = document.getElementById(tabletPreviewId);
       if (tabletPreview) {
         const tabletCanvas = this.cropper.getCroppedCanvas({
           width: 400,
           height: 160,
           imageSmoothingEnabled: true,
           imageSmoothingQuality: 'high'
         });
         tabletPreview.innerHTML = '';
         tabletCanvas.style.width = '100%';
         tabletCanvas.style.height = '100%';
         tabletCanvas.style.objectFit = 'cover';
         tabletPreview.appendChild(tabletCanvas);
       }
       
       // Update mobile preview (1-column grid - taller height)
       let mobilePreviewId;
       if (this.isEdit) {
         mobilePreviewId = 'editCropPreviewMobile';
       } else {
         mobilePreviewId = 'cropPreviewMobile';
       }
       const mobilePreview = document.getElementById(mobilePreviewId);
       if (mobilePreview) {
         const mobileCanvas = this.cropper.getCroppedCanvas({
           width: 500,
           height: 200,
           imageSmoothingEnabled: true,
           imageSmoothingQuality: 'high'
         });
         mobilePreview.innerHTML = '';
         mobileCanvas.style.width = '100%';
         mobileCanvas.style.height = '100%';
         mobileCanvas.style.objectFit = 'cover';
         mobilePreview.appendChild(mobileCanvas);
       }
    } catch (error) {
      console.error('Error updating device previews:', error);
    }
  }
  
  setupRealTimePreviews() {
    if (!this.cropper) return;
    
    // Use a polling approach to update previews in real-time
    let previewInterval;
    
    // Start polling for crop changes
    previewInterval = setInterval(() => {
      if (this.cropper && typeof this.cropper.getData === 'function') {
        try {
          this.updateDevicePreviews();
        } catch (error) {
          console.error('Error updating previews:', error);
          clearInterval(previewInterval);
        }
      }
    }, 100); // Update every 100ms
    
    // Store the interval ID so we can clear it later
    const intervalKey = this.isEdit ? 'editCropPreviewInterval' : 'cropPreviewInterval';
    window[intervalKey] = previewInterval;
    
    // Initial update
    setTimeout(() => {
      this.updateDevicePreviews();
    }, 200);
  }
  
  stopRealTimePreviews() {
    const intervalKey = this.isEdit ? 'editCropPreviewInterval' : 'cropPreviewInterval';
    if (window[intervalKey]) {
      clearInterval(window[intervalKey]);
      window[intervalKey] = null;
    }
  }
  
  showImagePreview(file) {
    // This method should be implemented by the parent class or passed as a callback
    // For now, we'll provide a basic implementation
    const validation = this.validateImageFile(file);
    
    if (!validation.valid) {
      console.error(validation.message);
      return;
    }
    
    const reader = new FileReader();
    reader.onload = (e) => {
      const imageUrl = e.target.result;
      const fileSizeMB = (file.size / (1024 * 1024)).toFixed(1);
      
      // Show basic preview with crop option
      const previewContainer = document.getElementById(this.isEdit ? 'currentImagePreview' : 'imagePreviewContainer');
      if (previewContainer) {
        previewContainer.innerHTML = `
          <div class="w-full h-full flex flex-col items-center justify-center">
            <img src="${imageUrl}" alt="Preview" class="max-h-16 max-w-full object-contain mb-2" />
            <p class="text-sm text-green-400">File selected: ${file.name}</p>
            <p class="text-xs text-gray-400">${fileSizeMB}MB</p>
            <button type="button" id="${this.isEdit ? 'edit' : ''}cropBtn" class="mt-2 px-3 py-1 bg-blue-600 text-white text-xs rounded hover:bg-blue-700 transition-colors">
              Crop Image
            </button>
          </div>
        `;
        
        // Add crop button functionality
        const cropBtn = document.getElementById((this.isEdit ? 'edit' : '') + 'cropBtn');
        if (cropBtn) {
          cropBtn.addEventListener('click', () => {
            console.log('Crop button clicked');
            this.showCropInterface(imageUrl, file);
          });
        } else {
          console.error('Crop button not found');
        }
      }
    };
    reader.readAsDataURL(file);
  }
  
  validateImageFile(file) {
    const maxSize = 2 * 1024 * 1024; // 2MB in bytes
    const allowedTypes = ['image/png', 'image/jpg', 'image/jpeg', 'image/gif', 'image/webp'];
    const bannedImageId = "bda5b4158afc4fb3b01dd6c34f67726b";
    
    // Check file size
    if (file.size > maxSize) {
      const sizeMB = (file.size / (1024 * 1024)).toFixed(1);
      return {
        valid: false,
        message: `File size (${sizeMB}MB) exceeds maximum allowed size of 2MB`
      };
    }
    
    // Check file type
    if (!allowedTypes.includes(file.type)) {
      return {
        valid: false,
        message: `File type ${file.type} is not allowed. Please use PNG, JPG, JPEG, GIF, or WebP.`
      };
    }
    
    // Check for banned image
    if (file.name.includes(bannedImageId)) {
      return {
        valid: false,
        message: 'This image is not allowed.'
      };
    }
    
    return { valid: true };
  }
}

// Export for use in other modules
if (typeof module !== 'undefined' && module.exports) {
  module.exports = ImageCropper;
} else {
  window.ImageCropper = ImageCropper;
} 