Project/
│
├── main.py                      # Entry point of the application
├── config.py                    # Global configuration settings
│
├── core/                        # Core application logic
│   ├── data_manager.py          # Handles data loading/saving
│   ├── capture_controller.py    # Controls data capture process
│   ├── realsense_service.py     # Interface for RealSense camera
│
└── ui/                          # User interface components
    ├── main_window.py           # Main application window
    └── tabs/                    # UI tabs
        ├── collection_tab.py    # Data collection interface
        ├── preprocess_tab.py    # Data preprocessing tools
        ├── annotate_tab.py      # Annotation interface
        ├── training_tab.py      # Model training interface
        └── analysis_tab.py      # Results analysis