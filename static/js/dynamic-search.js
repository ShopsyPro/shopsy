// Dynamic search functionality for shop pages
// This file contains the common search functionality used across all theme variants

document.addEventListener('DOMContentLoaded', function() {
    const searchInput = document.getElementById('shopSearchInput');
    const productGrid = document.querySelector('.grid.grid-cols-1.sm\\:grid-cols-2.lg\\:grid-cols-3.gap-6');
    const productCards = Array.from(document.querySelectorAll('.product-card'));
    
    if (searchInput && productCards.length > 0) {
        // Debounce function to limit API calls
        let searchTimeout;
        
        // OPTIMIZATION: Use document fragment and virtual scrolling for better performance
        let productData = []; // Cache product data for faster search
        
        // Pre-cache product data on page load
        productCards.forEach((card, index) => {
            const productName = card.querySelector('h3 button')?.textContent.toLowerCase() || '';
            const productDescription = card.querySelector('p')?.textContent.toLowerCase() || '';
            const productCategory = card.querySelector('.product-image span')?.textContent.toLowerCase() || '';
            
            productData[index] = {
                card: card,
                name: productName,
                description: productDescription,
                category: productCategory
            };
        });
        
        searchInput.addEventListener('input', function() {
            clearTimeout(searchTimeout);
            const searchTerm = this.value.toLowerCase().trim();
            
            // Show loading state only if there are many products
            if (productCards.length > 20) {
                productCards.forEach(card => {
                    card.style.opacity = '0.6';
                    card.style.pointerEvents = 'none';
                });
            }
            
            searchTimeout = setTimeout(() => {
                let visibleProductsCount = 0;
                const fragment = document.createDocumentFragment();
                const hiddenCards = [];
                
                // Use cached data for faster search
                productData.forEach((data, index) => {
                    const card = data.card;
                    const matches = searchTerm === '' || 
                        data.name.includes(searchTerm) || 
                        data.description.includes(searchTerm) ||
                        data.category.includes(searchTerm);
                    
                    if (matches) {
                        card.style.display = '';
                        card.style.opacity = '1';
                        card.style.pointerEvents = 'auto';
                        visibleProductsCount++;
                    } else {
                        card.style.display = 'none';
                        hiddenCards.push(card);
                    }
                });
                
                // Show/hide no products message
                if (visibleProductsCount === 0 && searchTerm) {
                    let existingMessage = document.getElementById('no-products-message');
                    if (!existingMessage) {
                        const messageDiv = document.createElement('div');
                        messageDiv.id = 'no-products-message';
                        messageDiv.className = 'text-center py-12 col-span-full';
                        
                        // Theme-specific styling for the no products message
                        const isDarkTheme = document.body.classList.contains('theme-dark-elegance');
                        const isClassicTheme = document.body.classList.contains('theme-classic');
                        
                        let messageHTML;
                        if (isDarkTheme) {
                            // Dark theme styling
                            messageHTML = `
                                <div class="bg-gradient-to-br from-gray-600 to-gray-700 p-6 rounded-2xl w-24 h-24 mx-auto mb-6 flex items-center justify-center">
                                    <svg class="w-12 h-12 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"></path>
                                    </svg>
                                </div>
                                <h3 class="text-xl font-bold text-white mb-3">No products match "${searchTerm}"</h3>
                                <p class="text-gray-400 max-w-md mx-auto text-sm leading-relaxed">Try a different search term or clear the search to see all products.</p>
                            `;
                        } else if (isClassicTheme) {
                            // Classic theme styling
                            messageHTML = `
                                <div class="bg-gradient-to-br from-gray-600 to-gray-700 p-6 rounded-2xl w-24 h-24 mx-auto mb-6 flex items-center justify-center">
                                    <svg class="w-12 h-12 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"></path>
                                    </svg>
                                </div>
                                <h3 class="text-xl font-bold text-white mb-3">No products match "${searchTerm}"</h3>
                                <p class="text-gray-400 max-w-md mx-auto text-sm leading-relaxed">Try a different search term or clear the search to see all products.</p>
                            `;
                        } else {
                            // Bold minimalist theme styling (default)
                            messageHTML = `
                                <div class="bg-gradient-to-br from-gray-200 to-gray-300 p-6 rounded-2xl w-24 h-24 mx-auto mb-6 flex items-center justify-center">
                                    <svg class="w-12 h-12 text-gray-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"></path>
                                    </svg>
                                </div>
                                <h3 class="text-xl font-bold text-gray-800 mb-3">No products match "${searchTerm}"</h3>
                                <p class="text-gray-600 max-w-md mx-auto text-sm leading-relaxed">Try a different search term or clear the search to see all products.</p>
                            `;
                        }
                        
                        messageDiv.innerHTML = messageHTML;
                        if (productGrid) {
                            productGrid.appendChild(messageDiv);
                        }
                    } else {
                        existingMessage.style.display = 'block';
                        existingMessage.querySelector('h3').textContent = `No products match "${searchTerm}"`;
                    }
                } else {
                    const existingMessage = document.getElementById('no-products-message');
                    if (existingMessage) {
                        existingMessage.style.display = 'none';
                    }
                }
            }, 300); // 300ms debounce
        });
        
        // Handle Enter key to submit search
        searchInput.addEventListener('keypress', function(e) {
            if (e.key === 'Enter') {
                e.preventDefault();
                const searchTerm = this.value.trim();
                if (searchTerm) {
                    // Update URL with search parameter
                    const url = new URL(window.location);
                    url.searchParams.set('search', searchTerm);
                    window.history.pushState({}, '', url);
                }
            }
        });

        // Clear search when input is empty
        searchInput.addEventListener('input', function() {
            if (this.value.trim() === '') {
                // Reset all products to visible using cached data
                productData.forEach((data) => {
                    data.card.style.display = '';
                    data.card.style.opacity = '1';
                    data.card.style.pointerEvents = 'auto';
                });
                
                // Hide no products message
                const existingMessage = document.getElementById('no-products-message');
                if (existingMessage) {
                    existingMessage.style.display = 'none';
                }
            }
        });
    }
});
