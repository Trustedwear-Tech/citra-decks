// FontCombinationsData.js - Curated font combinations for presentations
// Using Google Fonts for web-safe typography

// Font Categories
export const FONT_CATEGORIES = {
    PROFESSIONAL: 'professional',
    MODERN: 'modern',
    PLAYFUL: 'playful',
    ELEGANT: 'elegant',
    BOLD: 'bold',
};

export const CATEGORY_INFO = {
    [FONT_CATEGORIES.PROFESSIONAL]: { name: 'Professional', icon: 'briefcase-outline' },
    [FONT_CATEGORIES.MODERN]: { name: 'Modern', icon: 'trending-up-outline' },
    [FONT_CATEGORIES.PLAYFUL]: { name: 'Playful', icon: 'happy-outline' },
    [FONT_CATEGORIES.ELEGANT]: { name: 'Elegant', icon: 'sparkles-outline' },
    [FONT_CATEGORIES.BOLD]: { name: 'Bold', icon: 'megaphone-outline' },
};

// Curated font combinations inspired by Canva
export const FONT_COMBINATIONS = [
    // ==================== PROFESSIONAL ====================
    {
        id: 'pro_classic',
        name: 'Classic Professional',
        category: FONT_CATEGORIES.PROFESSIONAL,
        headingFont: { family: 'Playfair Display', weight: '700', style: 'normal' },
        bodyFont: { family: 'Open Sans', weight: '400', style: 'normal' },
        preview: { heading: 'PINOT NOIR', subheading: 'Marlborough', body: '2009' },
    },
    {
        id: 'pro_business',
        name: 'Business Solutions',
        category: FONT_CATEGORIES.PROFESSIONAL,
        headingFont: { family: 'Roboto Slab', weight: '600', style: 'normal' },
        bodyFont: { family: 'Roboto', weight: '400', style: 'normal' },
        preview: { heading: 'business', subheading: 'SOLUTIONS' },
    },
    {
        id: 'pro_corporate',
        name: 'Corporate Clean',
        category: FONT_CATEGORIES.PROFESSIONAL,
        headingFont: { family: 'Libre Baskerville', weight: '700', style: 'normal' },
        bodyFont: { family: 'Source Sans Pro', weight: '400', style: 'normal' },
        preview: { heading: 'QUARTERLY', subheading: 'Report 2024' },
    },
    {
        id: 'pro_executive',
        name: 'Executive',
        category: FONT_CATEGORIES.PROFESSIONAL,
        headingFont: { family: 'Lora', weight: '600', style: 'normal' },
        bodyFont: { family: 'Lato', weight: '400', style: 'normal' },
        preview: { heading: 'VALENCE', subheading: 'Square de la Couronne' },
    },

    // ==================== MODERN ====================
    {
        id: 'mod_minimal',
        name: 'Minimal Modern',
        category: FONT_CATEGORIES.MODERN,
        headingFont: { family: 'Montserrat', weight: '700', style: 'normal' },
        bodyFont: { family: 'Inter', weight: '400', style: 'normal' },
        preview: { heading: 'user', subheading: 'ORIENTED' },
    },
    {
        id: 'mod_tech',
        name: 'Tech Forward',
        category: FONT_CATEGORIES.MODERN,
        headingFont: { family: 'Poppins', weight: '600', style: 'normal' },
        bodyFont: { family: 'Work Sans', weight: '400', style: 'normal' },
        preview: { heading: 'COMING', subheading: 'SOON' },
    },
    {
        id: 'mod_startup',
        name: 'Startup Vibes',
        category: FONT_CATEGORIES.MODERN,
        headingFont: { family: 'Raleway', weight: '700', style: 'normal' },
        bodyFont: { family: 'Nunito Sans', weight: '400', style: 'normal' },
        preview: { heading: 'PLANET', subheading: 'ARCADIA' },
    },
    {
        id: 'mod_clean',
        name: 'Clean & Modern',
        category: FONT_CATEGORIES.MODERN,
        headingFont: { family: 'DM Sans', weight: '700', style: 'normal' },
        bodyFont: { family: 'DM Sans', weight: '400', style: 'normal' },
        preview: { heading: 'Title', subheading: 'HEADING', body: 'Paragraph' },
    },

    // ==================== PLAYFUL ====================
    {
        id: 'play_fun',
        name: 'Fun & Friendly',
        category: FONT_CATEGORIES.PLAYFUL,
        headingFont: { family: 'Fredoka One', weight: '400', style: 'normal' },
        bodyFont: { family: 'Nunito', weight: '400', style: 'normal' },
        preview: { heading: 'Play', subheading: 'time' },
    },
    {
        id: 'play_kids',
        name: 'Kids Party',
        category: FONT_CATEGORIES.PLAYFUL,
        headingFont: { family: 'Baloo 2', weight: '700', style: 'normal' },
        bodyFont: { family: 'Quicksand', weight: '500', style: 'normal' },
        preview: { heading: 'welcome', subheading: 'little one!' },
    },
    {
        id: 'play_creative',
        name: 'Creative Spirit',
        category: FONT_CATEGORIES.PLAYFUL,
        headingFont: { family: 'Righteous', weight: '400', style: 'normal' },
        bodyFont: { family: 'Comfortaa', weight: '400', style: 'normal' },
        preview: { heading: 'PUFF', subheading: 'LOVE' },
    },
    {
        id: 'play_casual',
        name: 'Casual Script',
        category: FONT_CATEGORIES.PLAYFUL,
        headingFont: { family: 'Pacifico', weight: '400', style: 'normal' },
        bodyFont: { family: 'Varela Round', weight: '400', style: 'normal' },
        preview: { heading: 'Save the Date', subheading: 'We are getting married' },
    },

    // ==================== ELEGANT ====================
    {
        id: 'ele_luxury',
        name: 'Luxury Serif',
        category: FONT_CATEGORIES.ELEGANT,
        headingFont: { family: 'Cormorant Garamond', weight: '600', style: 'normal' },
        bodyFont: { family: 'EB Garamond', weight: '400', style: 'normal' },
        preview: { heading: 'astrid', subheading: 'smith' },
    },
    {
        id: 'ele_wedding',
        name: 'Wedding Elegance',
        category: FONT_CATEGORIES.ELEGANT,
        headingFont: { family: 'Great Vibes', weight: '400', style: 'normal' },
        bodyFont: { family: 'Crimson Text', weight: '400', style: 'normal' },
        preview: { heading: 'Fab at Fifty!', subheading: 'October 15, 2026' },
    },
    {
        id: 'ele_classic',
        name: 'Timeless Classic',
        category: FONT_CATEGORIES.ELEGANT,
        headingFont: { family: 'Cinzel', weight: '600', style: 'normal' },
        bodyFont: { family: 'Spectral', weight: '400', style: 'normal' },
        preview: { heading: 'Legacies', subheading: 'A Story of Heritage' },
    },
    {
        id: 'ele_refined',
        name: 'Refined Beauty',
        category: FONT_CATEGORIES.ELEGANT,
        headingFont: { family: 'Italiana', weight: '400', style: 'normal' },
        bodyFont: { family: 'Cardo', weight: '400', style: 'normal' },
        preview: { heading: 'ESPRESSO', subheading: 'Café Menu' },
    },

    // ==================== BOLD ====================
    {
        id: 'bold_impact',
        name: 'Maximum Impact',
        category: FONT_CATEGORIES.BOLD,
        headingFont: { family: 'Oswald', weight: '700', style: 'normal' },
        bodyFont: { family: 'Barlow', weight: '400', style: 'normal' },
        preview: { heading: 'STEAK', subheading: 'NIGHT' },
    },
    {
        id: 'bold_power',
        name: 'Power Statement',
        category: FONT_CATEGORIES.BOLD,
        headingFont: { family: 'Anton', weight: '400', style: 'normal' },
        bodyFont: { family: 'Rubik', weight: '400', style: 'normal' },
        preview: { heading: 'FREE', subheading: 'DELIVERY' },
    },
    {
        id: 'bold_urban',
        name: 'Urban Edge',
        category: FONT_CATEGORIES.BOLD,
        headingFont: { family: 'Bebas Neue', weight: '400', style: 'normal' },
        bodyFont: { family: 'Archivo', weight: '400', style: 'normal' },
        preview: { heading: 'BIG AND', subheading: 'BOLD' },
    },
    {
        id: 'bold_sports',
        name: 'Sports Energy',
        category: FONT_CATEGORIES.BOLD,
        headingFont: { family: 'Black Ops One', weight: '400', style: 'normal' },
        bodyFont: { family: 'Exo 2', weight: '400', style: 'normal' },
        preview: { heading: 'THANK YOU', subheading: 'SO MUCH!' },
    },
];

// Get all unique font families for loading
export const getAllFontFamilies = () => {
    const families = new Set();
    FONT_COMBINATIONS.forEach(combo => {
        families.add(`${combo.headingFont.family}:wght@${combo.headingFont.weight}`);
        families.add(`${combo.bodyFont.family}:wght@${combo.bodyFont.weight}`);
    });
    return Array.from(families);
};

// Generate Google Fonts URL for loading
export const getGoogleFontsUrl = (families = null) => {
    const fontFamilies = families || getAllFontFamilies();
    const formattedFamilies = fontFamilies.map(f => f.replace(/ /g, '+')).join('&family=');
    return `https://fonts.googleapis.com/css2?family=${formattedFamilies}&display=swap`;
};

// Get fonts by category
export const getFontsByCategory = (category) => {
    return FONT_COMBINATIONS.filter(combo => combo.category === category);
};

// Load fonts dynamically
export const loadFonts = async (combinations = null) => {
    const combos = combinations || FONT_COMBINATIONS;
    const families = new Set();

    combos.forEach(combo => {
        families.add(`${combo.headingFont.family}:wght@${combo.headingFont.weight}`);
        families.add(`${combo.bodyFont.family}:wght@${combo.bodyFont.weight}`);
    });

    const url = getGoogleFontsUrl(Array.from(families));

    // Check if fonts are already loaded
    const existingLink = document.querySelector(`link[href="${url}"]`);
    if (existingLink) return Promise.resolve();

    return new Promise((resolve, reject) => {
        const link = document.createElement('link');
        link.rel = 'stylesheet';
        link.href = url;
        link.onload = () => resolve();
        link.onerror = () => reject(new Error('Failed to load fonts'));
        document.head.appendChild(link);
    });
};

export default FONT_COMBINATIONS;
