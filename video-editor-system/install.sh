#!/bin/bash

# Installation script for Video Editing Automation System
# Supports Ubuntu/Debian and macOS

set -e  # Exit on error

echo "======================================================================="
echo "VIDEO EDITING AUTOMATION SYSTEM - INSTALLATION SCRIPT"
echo "======================================================================="
echo ""

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to print colored output
print_success() {
    echo -e "${GREEN}✓${NC} $1"
}

print_error() {
    echo -e "${RED}✗${NC} $1"
}

print_info() {
    echo -e "${YELLOW}ℹ${NC} $1"
}

print_step() {
    echo ""
    echo "======================================================================="
    echo "$1"
    echo "======================================================================="
}

# Detect OS
OS="unknown"
if [[ "$OSTYPE" == "linux-gnu"* ]]; then
    OS="linux"
    print_info "Detected OS: Linux"
elif [[ "$OSTYPE" == "darwin"* ]]; then
    OS="mac"
    print_info "Detected OS: macOS"
else
    print_error "Unsupported operating system: $OSTYPE"
    exit 1
fi

# STEP 1: Check Python
print_step "STEP 1: Checking Python Installation"

if ! command -v python3 &> /dev/null; then
    print_error "Python 3 is not installed"
    echo "Please install Python 3.8 or higher:"
    if [ "$OS" == "linux" ]; then
        echo "  sudo apt update && sudo apt install python3 python3-pip"
    elif [ "$OS" == "mac" ]; then
        echo "  brew install python3"
    fi
    exit 1
fi

PYTHON_VERSION=$(python3 --version | cut -d ' ' -f 2)
print_success "Python $PYTHON_VERSION is installed"

# Check pip
if ! command -v pip3 &> /dev/null; then
    print_error "pip3 is not installed"
    echo "Please install pip3:"
    if [ "$OS" == "linux" ]; then
        echo "  sudo apt install python3-pip"
    elif [ "$OS" == "mac" ]; then
        echo "  python3 -m ensurepip"
    fi
    exit 1
fi

print_success "pip3 is installed"

# STEP 2: Check FFmpeg
print_step "STEP 2: Checking FFmpeg Installation"

if ! command -v ffmpeg &> /dev/null; then
    print_error "FFmpeg is not installed"
    echo ""
    echo "Installing FFmpeg..."

    if [ "$OS" == "linux" ]; then
        if command -v apt &> /dev/null; then
            sudo apt update
            sudo apt install -y ffmpeg
        elif command -v yum &> /dev/null; then
            sudo yum install -y ffmpeg
        else
            print_error "Cannot install FFmpeg automatically. Please install manually:"
            echo "  Ubuntu/Debian: sudo apt install ffmpeg"
            echo "  CentOS/RHEL: sudo yum install ffmpeg"
            exit 1
        fi
    elif [ "$OS" == "mac" ]; then
        if command -v brew &> /dev/null; then
            brew install ffmpeg
        else
            print_error "Homebrew not found. Please install FFmpeg manually:"
            echo "  Install Homebrew: /bin/bash -c \"\$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)\""
            echo "  Then run: brew install ffmpeg"
            exit 1
        fi
    fi

    # Verify installation
    if ! command -v ffmpeg &> /dev/null; then
        print_error "FFmpeg installation failed"
        exit 1
    fi
fi

FFMPEG_VERSION=$(ffmpeg -version | head -n 1 | cut -d ' ' -f 3)
print_success "FFmpeg $FFMPEG_VERSION is installed"

if ! command -v ffprobe &> /dev/null; then
    print_error "FFprobe is not installed (should come with FFmpeg)"
    exit 1
fi

print_success "FFprobe is installed"

# STEP 3: Create virtual environment (optional but recommended)
print_step "STEP 3: Setting Up Python Virtual Environment"

if [ -d "venv" ]; then
    print_info "Virtual environment already exists"
else
    print_info "Creating virtual environment..."
    python3 -m venv venv
    print_success "Virtual environment created"
fi

# Activate virtual environment
print_info "Activating virtual environment..."
source venv/bin/activate
print_success "Virtual environment activated"

# STEP 4: Install Python dependencies
print_step "STEP 4: Installing Python Dependencies"

print_info "Upgrading pip..."
pip install --upgrade pip

print_info "Installing required packages (this may take several minutes)..."
pip install -r requirements.txt

print_success "All Python dependencies installed"

# STEP 5: Verify installations
print_step "STEP 5: Verifying Installation"

print_info "Verifying Flask installation..."
python3 -c "import flask; print('Flask version:', flask.__version__)" && print_success "Flask OK"

print_info "Verifying Whisper installation..."
python3 -c "import whisper; print('Whisper OK')" && print_success "Whisper OK"

print_info "Verifying FFmpeg Python bindings..."
python3 -c "import ffmpeg; print('ffmpeg-python OK')" && print_success "ffmpeg-python OK"

# STEP 6: Create necessary directories
print_step "STEP 6: Creating Required Directories"

mkdir -p uploads temp output sample_data

print_success "Created: uploads/"
print_success "Created: temp/"
print_success "Created: output/"
print_success "Created: sample_data/"

# STEP 7: Test FFmpeg functionality
print_step "STEP 7: Testing FFmpeg Functionality"

print_info "Running FFmpeg test..."
python3 -c "
import subprocess
import sys
try:
    subprocess.run(['ffmpeg', '-version'], capture_output=True, check=True)
    subprocess.run(['ffprobe', '-version'], capture_output=True, check=True)
    print('FFmpeg tests passed')
except Exception as e:
    print(f'FFmpeg test failed: {e}', file=sys.stderr)
    sys.exit(1)
" && print_success "FFmpeg functionality verified"

# STEP 8: Final summary
print_step "INSTALLATION COMPLETE"

echo ""
print_success "All components installed successfully!"
echo ""
echo "======================================================================="
echo "NEXT STEPS:"
echo "======================================================================="
echo ""
echo "1. Start the API server:"
echo "   python3 backend/api.py"
echo ""
echo "2. Open your browser to:"
echo "   http://localhost:5000"
echo ""
echo "3. Or use the backend directly:"
echo "   python3 backend/main.py"
echo ""
echo "======================================================================="
echo "NOTES:"
echo "======================================================================="
echo ""
echo "• Virtual environment is in: ./venv"
echo "• To activate it: source venv/bin/activate"
echo "• To deactivate: deactivate"
echo ""
echo "• Upload files to: ./uploads"
echo "• Output videos in: ./output"
echo "• Temporary files in: ./temp"
echo ""
echo "• For sample data, add test files to: ./sample_data"
echo ""
echo "======================================================================="
echo ""

print_success "Installation script completed successfully!"
echo ""
