
class ColorConfig:
    """
    Centralized configuration for application colors.
    """
    # Item Status Backgrounds
    PKG_BG = '#fff4b8'  # Yellow (Packaged)
    STK_BG = '#dcecff'  # Blue (Sticker)
    BOTH_BG = '#d6f5d6' # Green (Both)
    NONE_BG = '#ffffff' # White (None)

    # Selection Backgrounds
    SEL_DEFAULT = '#808080' # Grey
    SEL_PKG = '#e6dbaa'     # Darker Yellow
    SEL_STK = '#b8d4f5'     # Darker Blue
    SEL_BOTH = '#b8e6b8'    # Darker Green

    # Selection Text Colors
    SEL_FG_DEFAULT = 'white'
    SEL_FG_DARK = 'black'

    # Borders
    BORDER_DEFAULT = '#555555'
    BORDER_PKG = '#c4b88a'
    BORDER_STK = '#98b4d5'
    BORDER_BOTH = '#98c698'
    BORDER_FOCUS = 'black'

    @classmethod
    def get_tag_config(cls):
        """Returns the tag configuration dictionary for Treeview."""
        return {
            'none': {'bg': cls.NONE_BG},
            'packaged': {'bg': cls.PKG_BG},
            'sticker': {'bg': cls.STK_BG},
            'both': {'bg': cls.BOTH_BG}
        }

    @classmethod
    def get_status_tag(cls, pkg: int, stk: int) -> str:
        """Determines the tag name based on status flags."""
        if pkg and stk: return 'both'
        if pkg: return 'packaged'
        if stk: return 'sticker'
        return 'none'
