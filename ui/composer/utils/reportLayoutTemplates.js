/**
 * Report Layout Templates - Predefined page layouts for reports
 * 
 * Each template defines:
 * - name: Display name for UI
 * - description: Short description
 * - icon: MaterialIcons icon name
 * - cssClass: CSS class for styling
 * - columns: Number of columns
 * - gridAreas: Named areas for content placement
 * - hasImageSlot: Whether layout has dedicated image area
 * 
 * Unlike presentations (Fabric.js with fixed pixel positions),
 * reports use HTML/CSS with flexible grid/flexbox layouts.
 */

// ==================== Layout Definitions ====================

export const REPORT_PAGE_LAYOUTS = {
  // -------------------- Basic Layouts --------------------
  single_column: {
    id: 'single_column',
    name: 'Single Column',
    description: 'Full-width content flow - ideal for narrative text',
    icon: 'view-agenda',
    cssClass: 'layout-single',
    columns: 1,
    thumbnail: 'single',
    gridAreas: ['main'],
    gridTemplate: '1fr',
    category: 'basic',
  },

  two_columns: {
    id: 'two_columns',
    name: 'Two Columns',
    description: 'Side-by-side content areas for comparisons',
    icon: 'view-column',
    cssClass: 'layout-two-col',
    columns: 2,
    thumbnail: 'two-col',
    gridAreas: ['left', 'right'],
    gridTemplate: '1fr 1fr',
    gap: '24px',
    category: 'basic',
  },

  three_columns: {
    id: 'three_columns',
    name: 'Three Columns',
    description: 'Triple column layout for data and KPIs',
    icon: 'view-week',
    cssClass: 'layout-three-col',
    columns: 3,
    thumbnail: 'three-col',
    gridAreas: ['col1', 'col2', 'col3'],
    gridTemplate: '1fr 1fr 1fr',
    gap: '20px',
    category: 'basic',
  },

  // -------------------- Media Layouts (With Images) --------------------
  two_columns_image_left: {
    id: 'two_columns_image_left',
    name: 'Image Left + Text',
    description: 'Featured image with content on right',
    icon: 'photo-library',
    cssClass: 'layout-img-left',
    columns: 2,
    hasImageSlot: true,
    imagePosition: 'left',
    thumbnail: 'img-left',
    gridAreas: ['image', 'content'],
    gridTemplate: '40% 1fr',
    gap: '24px',
    category: 'media',
  },

  two_columns_image_right: {
    id: 'two_columns_image_right',
    name: 'Text + Image Right',
    description: 'Content with featured image on right',
    icon: 'photo-library',
    cssClass: 'layout-img-right',
    columns: 2,
    hasImageSlot: true,
    imagePosition: 'right',
    thumbnail: 'img-right',
    gridAreas: ['content', 'image'],
    gridTemplate: '1fr 40%',
    gap: '24px',
    category: 'media',
  },

  hero_section: {
    id: 'hero_section',
    name: 'Hero Section',
    description: 'Large image/title with content below',
    icon: 'web-asset',
    cssClass: 'layout-hero',
    columns: 1,
    hasImageSlot: true,
    imagePosition: 'top',
    thumbnail: 'hero',
    gridAreas: ['hero', 'content'],
    gridTemplate: 'auto 1fr',
    gridDirection: 'column',
    gap: '24px',
    category: 'media',
  },

  image_grid: {
    id: 'image_grid',
    name: 'Image Gallery',
    description: 'Multiple images with captions',
    icon: 'collections',
    cssClass: 'layout-image-grid',
    columns: 2,
    hasImageSlot: true,
    multipleImages: true,
    thumbnail: 'gallery',
    gridAreas: ['img1', 'img2', 'img3', 'img4'],
    gridTemplate: '1fr 1fr',
    gridRows: 'auto auto',
    gap: '16px',
    category: 'media',
  },

  // -------------------- Advanced Layouts --------------------
  sidebar_layout: {
    id: 'sidebar_layout',
    name: 'Content + Sidebar',
    description: 'Main content with sidebar for notes/highlights',
    icon: 'view-sidebar',
    cssClass: 'layout-sidebar',
    columns: 2,
    thumbnail: 'sidebar',
    gridAreas: ['main', 'sidebar'],
    gridTemplate: '70% 30%',
    gap: '24px',
    category: 'advanced',
  },

  sidebar_left: {
    id: 'sidebar_left',
    name: 'Sidebar + Content',
    description: 'Sidebar on left with main content',
    icon: 'vertical-split',
    cssClass: 'layout-sidebar-left',
    columns: 2,
    thumbnail: 'sidebar-left',
    gridAreas: ['sidebar', 'main'],
    gridTemplate: '30% 70%',
    gap: '24px',
    category: 'advanced',
  },

  dashboard: {
    id: 'dashboard',
    name: 'Dashboard Grid',
    description: 'Four quadrant layout for charts/KPIs',
    icon: 'grid-view',
    cssClass: 'layout-dashboard',
    columns: 2,
    rows: 2,
    thumbnail: 'dashboard',
    gridAreas: ['tl', 'tr', 'bl', 'br'],
    gridTemplate: '1fr 1fr',
    gridRows: '1fr 1fr',
    gap: '20px',
    category: 'advanced',
  },

  infographic: {
    id: 'infographic',
    name: 'Infographic',
    description: 'Visual-heavy layout for data storytelling',
    icon: 'insights',
    cssClass: 'layout-infographic',
    columns: 1,
    hasImageSlot: true,
    thumbnail: 'infographic',
    gridAreas: ['title', 'visual', 'stats', 'content'],
    gridTemplate: '1fr',
    gridDirection: 'column',
    gap: '20px',
    category: 'advanced',
  },

  executive_summary: {
    id: 'executive_summary',
    name: 'Executive Summary',
    description: 'Key highlights with supporting details',
    icon: 'summarize',
    cssClass: 'layout-exec-summary',
    columns: 1,
    thumbnail: 'exec-summary',
    gridAreas: ['highlights', 'details'],
    gridTemplate: '1fr',
    gridDirection: 'column',
    gap: '32px',
    category: 'advanced',
  },

  // -------------------- AI Auto Layout --------------------
  ai_auto: {
    id: 'ai_auto',
    name: 'Let AI Decide',
    description: 'AI will choose the best layout based on content',
    icon: 'auto-awesome',
    cssClass: 'layout-auto',
    isAIDecide: true,
    thumbnail: 'ai',
    category: 'ai',
  },
};

// ==================== Layout Categories ====================

export const LAYOUT_CATEGORIES = [
  { 
    id: 'ai', 
    name: 'AI', 
    icon: 'auto-awesome',
    description: 'Let AI choose the best layout',
    layouts: ['ai_auto'] 
  },
  { 
    id: 'basic', 
    name: 'Basic', 
    icon: 'view-agenda',
    description: 'Simple column layouts',
    layouts: ['single_column', 'two_columns', 'three_columns'] 
  },
  { 
    id: 'media', 
    name: 'With Images', 
    icon: 'photo-library',
    description: 'Layouts featuring images',
    layouts: ['two_columns_image_left', 'two_columns_image_right', 'hero_section', 'image_grid'] 
  },
  { 
    id: 'advanced', 
    name: 'Advanced', 
    icon: 'dashboard',
    description: 'Complex multi-section layouts',
    layouts: ['sidebar_layout', 'sidebar_left', 'dashboard', 'infographic', 'executive_summary'] 
  },
];

// ==================== CSS Generation ====================

/**
 * Generate inline CSS for a specific layout
 * @param {string} layoutId - The layout ID
 * @returns {string} CSS string for the layout container
 */
export const getLayoutCSS = (layoutId) => {
  const layout = REPORT_PAGE_LAYOUTS[layoutId];
  if (!layout || layout.isAIDecide) return '';

  const gap = layout.gap || '24px';
  
  switch (layoutId) {
    case 'single_column':
      return `display: block;`;
      
    case 'two_columns':
      return `display: grid; grid-template-columns: 1fr 1fr; gap: ${gap};`;
      
    case 'three_columns':
      return `display: grid; grid-template-columns: 1fr 1fr 1fr; gap: ${gap};`;
      
    case 'two_columns_image_left':
      return `display: grid; grid-template-columns: 40% 1fr; gap: ${gap}; align-items: start;`;
      
    case 'two_columns_image_right':
      return `display: grid; grid-template-columns: 1fr 40%; gap: ${gap}; align-items: start;`;
      
    case 'sidebar_layout':
      return `display: grid; grid-template-columns: 70% 30%; gap: ${gap};`;
      
    case 'sidebar_left':
      return `display: grid; grid-template-columns: 30% 70%; gap: ${gap};`;
      
    case 'dashboard':
      return `display: grid; grid-template-columns: 1fr 1fr; grid-template-rows: 1fr 1fr; gap: ${gap};`;
      
    case 'hero_section':
      return `display: flex; flex-direction: column; gap: ${gap};`;
      
    case 'image_grid':
      return `display: grid; grid-template-columns: 1fr 1fr; grid-template-rows: auto auto; gap: 16px;`;
      
    case 'infographic':
      return `display: flex; flex-direction: column; gap: ${gap}; text-align: center;`;
      
    case 'executive_summary':
      return `display: flex; flex-direction: column; gap: 32px;`;
      
    default:
      return `display: block;`;
  }
};

/**
 * Generate HTML structure for a layout with placeholders
 * Uses tables for multi-column layouts since TipTap natively supports tables.
 * @param {string} layoutId - The layout ID
 * @param {object} content - Content for each grid area
 * @returns {string} HTML string with layout structure
 */
export const generateLayoutHTML = (layoutId, content = {}) => {
  const layout = REPORT_PAGE_LAYOUTS[layoutId];
  
  // Single column or AI auto - return empty for default TipTap behavior
  if (!layout || layout.isAIDecide || layoutId === 'single_column') {
    return content.main || '';
  }

  const columns = layout.columns || 1;
  const areas = layout.gridAreas || ['main'];
  
  // Use tables for multi-column layouts (TipTap supports tables natively)
  if (columns >= 2) {
    // Calculate column width percentage
    const colWidth = Math.floor(100 / columns);
    
    let html = `<table style="width: 100%; border-collapse: collapse; table-layout: fixed;">`;
    html += `<tbody><tr>`;
    
    areas.forEach((area, index) => {
      const areaContent = content[area] || `<p>Click to add content...</p>`;
      const isImageArea = layout.hasImageSlot && (area === 'image' || area === 'hero' || area.startsWith('img'));
      
      // Different styling for image vs content areas
      const cellStyle = isImageArea 
        ? `width: ${layout.imagePosition === 'left' || layout.imagePosition === 'right' ? '40%' : colWidth + '%'}; padding: 16px; vertical-align: top; background-color: #f8fafc;`
        : `width: ${colWidth}%; padding: 16px; vertical-align: top;`;
      
      html += `<td style="${cellStyle}">${areaContent}</td>`;
    });
    
    html += `</tr></tbody></table>`;
    return html;
  }
  
  // Fallback for other layouts - just return content
  return content.main || '';
};

/**
 * Get layout by ID with fallback to single column
 * @param {string} layoutId 
 * @returns {object} Layout definition
 */
export const getLayoutById = (layoutId) => {
  return REPORT_PAGE_LAYOUTS[layoutId] || REPORT_PAGE_LAYOUTS.single_column;
};

/**
 * Get layouts by category
 * @param {string} categoryId 
 * @returns {array} Array of layout definitions
 */
export const getLayoutsByCategory = (categoryId) => {
  const category = LAYOUT_CATEGORIES.find(c => c.id === categoryId);
  if (!category) return [];
  return category.layouts.map(id => REPORT_PAGE_LAYOUTS[id]).filter(Boolean);
};

/**
 * Check if a layout has image slots
 * @param {string} layoutId 
 * @returns {boolean}
 */
export const layoutHasImages = (layoutId) => {
  const layout = REPORT_PAGE_LAYOUTS[layoutId];
  return layout?.hasImageSlot || false;
};

/**
 * Get the number of image slots in a layout
 * @param {string} layoutId 
 * @returns {number}
 */
export const getImageSlotCount = (layoutId) => {
  const layout = REPORT_PAGE_LAYOUTS[layoutId];
  if (!layout?.hasImageSlot) return 0;
  if (layout.multipleImages) {
    return layout.gridAreas.filter(a => a.startsWith('img')).length;
  }
  return 1;
};

// ==================== Global Layout Styles ====================

/**
 * Generate global CSS for all layouts (to be injected into document)
 * @param {object} styleConfig - Optional style configuration
 * @returns {string} CSS string
 */
export const generateGlobalLayoutCSS = (styleConfig = {}) => {
  const primaryColor = styleConfig.primaryColor || '#3B82F6';
  const borderColor = styleConfig.borderColor || '#E5E7EB';
  const cardBg = styleConfig.cardBackground || '#F9FAFB';
  
  return `
    /* Report Layout System - Global Styles */
    .layout-container {
      width: 100%;
      min-height: 100px;
    }
    
    .layout-area {
      min-height: 50px;
      position: relative;
    }
    
    .layout-area-content {
      padding: 0;
    }
    
    .layout-area-image {
      display: flex;
      align-items: center;
      justify-content: center;
      background-color: ${cardBg};
      border: 2px dashed ${borderColor};
      border-radius: 8px;
      min-height: 200px;
      overflow: hidden;
    }
    
    .layout-area-image img {
      max-width: 100%;
      max-height: 100%;
      object-fit: contain;
      border-radius: 6px;
    }
    
    .layout-area-image.has-image {
      border: none;
      background: transparent;
    }
    
    .layout-area .placeholder {
      color: #9CA3AF;
      font-style: italic;
      text-align: center;
      padding: 20px;
      cursor: pointer;
    }
    
    /* Single Column */
    .layout-single {
      display: block;
    }
    
    /* Two Columns */
    .layout-two-col {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 24px;
    }
    
    /* Three Columns */
    .layout-three-col {
      display: grid;
      grid-template-columns: 1fr 1fr 1fr;
      gap: 20px;
    }
    
    /* Image Left */
    .layout-img-left {
      display: grid;
      grid-template-columns: 40% 1fr;
      gap: 24px;
      align-items: start;
    }
    
    /* Image Right */
    .layout-img-right {
      display: grid;
      grid-template-columns: 1fr 40%;
      gap: 24px;
      align-items: start;
    }
    
    /* Sidebar Right */
    .layout-sidebar {
      display: grid;
      grid-template-columns: 70% 30%;
      gap: 24px;
    }
    
    .layout-sidebar [data-area="sidebar"] {
      background-color: ${cardBg};
      padding: 16px;
      border-radius: 8px;
      border: 1px solid ${borderColor};
    }
    
    /* Sidebar Left */
    .layout-sidebar-left {
      display: grid;
      grid-template-columns: 30% 70%;
      gap: 24px;
    }
    
    .layout-sidebar-left [data-area="sidebar"] {
      background-color: ${cardBg};
      padding: 16px;
      border-radius: 8px;
      border: 1px solid ${borderColor};
    }
    
    /* Dashboard Grid */
    .layout-dashboard {
      display: grid;
      grid-template-columns: 1fr 1fr;
      grid-template-rows: 1fr 1fr;
      gap: 20px;
    }
    
    .layout-dashboard .layout-area {
      background-color: ${cardBg};
      padding: 16px;
      border-radius: 8px;
      border: 1px solid ${borderColor};
    }
    
    /* Hero Section */
    .layout-hero {
      display: flex;
      flex-direction: column;
      gap: 24px;
    }
    
    .layout-hero [data-area="hero"] {
      min-height: 300px;
      background-color: ${cardBg};
      border-radius: 12px;
      overflow: hidden;
    }
    
    .layout-hero [data-area="hero"] img {
      width: 100%;
      height: 100%;
      object-fit: cover;
    }
    
    /* Image Grid */
    .layout-image-grid {
      display: grid;
      grid-template-columns: 1fr 1fr;
      grid-template-rows: auto auto;
      gap: 16px;
    }
    
    .layout-image-grid .layout-area-image {
      min-height: 180px;
    }
    
    /* Infographic */
    .layout-infographic {
      display: flex;
      flex-direction: column;
      gap: 20px;
      text-align: center;
    }
    
    .layout-infographic [data-area="visual"] {
      min-height: 250px;
    }
    
    .layout-infographic [data-area="stats"] {
      display: flex;
      justify-content: space-around;
      flex-wrap: wrap;
      gap: 16px;
    }
    
    /* Executive Summary */
    .layout-exec-summary {
      display: flex;
      flex-direction: column;
      gap: 32px;
    }
    
    .layout-exec-summary [data-area="highlights"] {
      background: linear-gradient(135deg, ${primaryColor}10, ${primaryColor}05);
      border-left: 4px solid ${primaryColor};
      padding: 20px 24px;
      border-radius: 0 8px 8px 0;
    }
    
    /* Responsive adjustments */
    @media (max-width: 768px) {
      .layout-two-col,
      .layout-three-col,
      .layout-img-left,
      .layout-img-right,
      .layout-sidebar,
      .layout-sidebar-left,
      .layout-dashboard {
        grid-template-columns: 1fr;
      }
      
      .layout-image-grid {
        grid-template-columns: 1fr;
      }
    }
    
    /* Print styles */
    @media print {
      .layout-container {
        page-break-inside: avoid;
      }
      
      .layout-area-image {
        border: 1px solid #ddd;
      }
    }
  `;
};

// ==================== Layout Thumbnails for Picker ====================

/**
 * SVG thumbnail representations for layout picker
 */
export const LAYOUT_THUMBNAILS = {
  single_column: `
    <svg viewBox="0 0 80 60" fill="none">
      <rect x="10" y="8" width="60" height="8" rx="2" fill="currentColor" opacity="0.8"/>
      <rect x="10" y="20" width="60" height="4" rx="1" fill="currentColor" opacity="0.4"/>
      <rect x="10" y="28" width="60" height="4" rx="1" fill="currentColor" opacity="0.4"/>
      <rect x="10" y="36" width="60" height="4" rx="1" fill="currentColor" opacity="0.4"/>
      <rect x="10" y="44" width="40" height="4" rx="1" fill="currentColor" opacity="0.4"/>
    </svg>
  `,
  two_columns: `
    <svg viewBox="0 0 80 60" fill="none">
      <rect x="6" y="8" width="32" height="44" rx="2" fill="currentColor" opacity="0.15"/>
      <rect x="42" y="8" width="32" height="44" rx="2" fill="currentColor" opacity="0.15"/>
      <rect x="10" y="12" width="24" height="4" rx="1" fill="currentColor" opacity="0.6"/>
      <rect x="10" y="20" width="24" height="3" rx="1" fill="currentColor" opacity="0.3"/>
      <rect x="10" y="26" width="24" height="3" rx="1" fill="currentColor" opacity="0.3"/>
      <rect x="46" y="12" width="24" height="4" rx="1" fill="currentColor" opacity="0.6"/>
      <rect x="46" y="20" width="24" height="3" rx="1" fill="currentColor" opacity="0.3"/>
      <rect x="46" y="26" width="24" height="3" rx="1" fill="currentColor" opacity="0.3"/>
    </svg>
  `,
  three_columns: `
    <svg viewBox="0 0 80 60" fill="none">
      <rect x="4" y="8" width="22" height="44" rx="2" fill="currentColor" opacity="0.15"/>
      <rect x="29" y="8" width="22" height="44" rx="2" fill="currentColor" opacity="0.15"/>
      <rect x="54" y="8" width="22" height="44" rx="2" fill="currentColor" opacity="0.15"/>
      <rect x="7" y="12" width="16" height="3" rx="1" fill="currentColor" opacity="0.6"/>
      <rect x="7" y="18" width="16" height="2" rx="1" fill="currentColor" opacity="0.3"/>
      <rect x="32" y="12" width="16" height="3" rx="1" fill="currentColor" opacity="0.6"/>
      <rect x="32" y="18" width="16" height="2" rx="1" fill="currentColor" opacity="0.3"/>
      <rect x="57" y="12" width="16" height="3" rx="1" fill="currentColor" opacity="0.6"/>
      <rect x="57" y="18" width="16" height="2" rx="1" fill="currentColor" opacity="0.3"/>
    </svg>
  `,
  'img-left': `
    <svg viewBox="0 0 80 60" fill="none">
      <rect x="6" y="8" width="28" height="44" rx="2" fill="currentColor" opacity="0.2"/>
      <path d="M14 30 L20 24 L26 32 L30 28" stroke="currentColor" opacity="0.5" stroke-width="1.5" fill="none"/>
      <circle cx="14" cy="18" r="3" fill="currentColor" opacity="0.4"/>
      <rect x="38" y="8" width="36" height="6" rx="1" fill="currentColor" opacity="0.7"/>
      <rect x="38" y="18" width="36" height="3" rx="1" fill="currentColor" opacity="0.3"/>
      <rect x="38" y="24" width="36" height="3" rx="1" fill="currentColor" opacity="0.3"/>
      <rect x="38" y="30" width="36" height="3" rx="1" fill="currentColor" opacity="0.3"/>
      <rect x="38" y="36" width="24" height="3" rx="1" fill="currentColor" opacity="0.3"/>
    </svg>
  `,
  'img-right': `
    <svg viewBox="0 0 80 60" fill="none">
      <rect x="6" y="8" width="36" height="6" rx="1" fill="currentColor" opacity="0.7"/>
      <rect x="6" y="18" width="36" height="3" rx="1" fill="currentColor" opacity="0.3"/>
      <rect x="6" y="24" width="36" height="3" rx="1" fill="currentColor" opacity="0.3"/>
      <rect x="6" y="30" width="36" height="3" rx="1" fill="currentColor" opacity="0.3"/>
      <rect x="6" y="36" width="24" height="3" rx="1" fill="currentColor" opacity="0.3"/>
      <rect x="46" y="8" width="28" height="44" rx="2" fill="currentColor" opacity="0.2"/>
      <path d="M54 30 L60 24 L66 32 L70 28" stroke="currentColor" opacity="0.5" stroke-width="1.5" fill="none"/>
      <circle cx="54" cy="18" r="3" fill="currentColor" opacity="0.4"/>
    </svg>
  `,
  hero: `
    <svg viewBox="0 0 80 60" fill="none">
      <rect x="6" y="6" width="68" height="28" rx="2" fill="currentColor" opacity="0.2"/>
      <path d="M20 22 L30 14 L45 26 L55 18 L68 28" stroke="currentColor" opacity="0.5" stroke-width="1.5" fill="none"/>
      <circle cx="18" cy="14" r="4" fill="currentColor" opacity="0.4"/>
      <rect x="6" y="38" width="68" height="4" rx="1" fill="currentColor" opacity="0.6"/>
      <rect x="6" y="46" width="68" height="3" rx="1" fill="currentColor" opacity="0.3"/>
      <rect x="6" y="52" width="48" height="3" rx="1" fill="currentColor" opacity="0.3"/>
    </svg>
  `,
  sidebar: `
    <svg viewBox="0 0 80 60" fill="none">
      <rect x="6" y="8" width="48" height="44" rx="2" fill="currentColor" opacity="0.1"/>
      <rect x="58" y="8" width="16" height="44" rx="2" fill="currentColor" opacity="0.2"/>
      <rect x="10" y="12" width="40" height="5" rx="1" fill="currentColor" opacity="0.6"/>
      <rect x="10" y="20" width="40" height="3" rx="1" fill="currentColor" opacity="0.3"/>
      <rect x="10" y="26" width="40" height="3" rx="1" fill="currentColor" opacity="0.3"/>
      <rect x="61" y="12" width="10" height="3" rx="1" fill="currentColor" opacity="0.5"/>
      <rect x="61" y="18" width="10" height="3" rx="1" fill="currentColor" opacity="0.3"/>
      <rect x="61" y="24" width="10" height="3" rx="1" fill="currentColor" opacity="0.3"/>
    </svg>
  `,
  dashboard: `
    <svg viewBox="0 0 80 60" fill="none">
      <rect x="6" y="6" width="32" height="22" rx="2" fill="currentColor" opacity="0.15"/>
      <rect x="42" y="6" width="32" height="22" rx="2" fill="currentColor" opacity="0.15"/>
      <rect x="6" y="32" width="32" height="22" rx="2" fill="currentColor" opacity="0.15"/>
      <rect x="42" y="32" width="32" height="22" rx="2" fill="currentColor" opacity="0.15"/>
      <rect x="10" y="10" width="12" height="8" rx="1" fill="currentColor" opacity="0.4"/>
      <rect x="46" y="10" width="24" height="3" rx="1" fill="currentColor" opacity="0.5"/>
      <rect x="10" y="36" width="24" height="3" rx="1" fill="currentColor" opacity="0.5"/>
      <circle cx="58" cy="43" r="6" stroke="currentColor" opacity="0.4" stroke-width="2" fill="none"/>
    </svg>
  `,
  ai: `
    <svg viewBox="0 0 80 60" fill="none">
      <circle cx="40" cy="30" r="18" stroke="currentColor" opacity="0.3" stroke-width="2" fill="none"/>
      <path d="M40 16 L42 24 L50 22 L46 28 L54 30 L46 32 L50 38 L42 36 L40 44 L38 36 L30 38 L34 32 L26 30 L34 28 L30 22 L38 24 Z" fill="currentColor" opacity="0.6"/>
    </svg>
  `,
};

export default REPORT_PAGE_LAYOUTS;
