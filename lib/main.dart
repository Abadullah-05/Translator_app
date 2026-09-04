import 'package:flutter/foundation.dart'; // kIsWeb ke liye
import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;
import 'package:file_picker/file_picker.dart';
import 'dart:convert';
import 'package:url_launcher/url_launcher.dart'; // Web aur Mobile dono ke liye safe package

void main() {
  runApp(const MyApp());
}

class MyApp extends StatelessWidget {
  const MyApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Neural Voice-Match Dubber Studio',
      theme: ThemeData(
        primarySwatch: Colors.deepPurple,
        useMaterial3: true,
      ),
      home: const TranslatorHomePage(),
    );
  }
}

class TranslatorHomePage extends StatefulWidget {
  const TranslatorHomePage({super.key});

  @override
  State<TranslatorHomePage> createState() => _TranslatorHomePageState();
}

class _TranslatorHomePageState extends State<TranslatorHomePage> {
  PlatformFile? _selectedFile;

  String _originalLanguage = 'Auto-Detect';
  String? _targetLanguage; // Shuru mein khali (null) rahega

  bool _isLoading = false;
  String _statusMessage = '';
  bool _isCompleted = false;

  final List<String> elevenLabsLanguages = [
    'Auto-Detect',
    'English',
    'Hindi',
    'Spanish',
    'French',
    'German',
    'Japanese',
    'Chinese',
    'Portuguese',
    'Italian',
    'Polish',
    'Turkish',
    'Dutch',
    'Korean',
    'Arabic',
    'Swedish',
    'Indonesian',
    'Filipino',
    'Romanian',
    'Ukrainian',
    'Greek',
    'Czech',
    'Danish',
    'Finnish',
    'Bulgarian',
    'Croatian',
    'Slovak',
    'Tamil',
    'Hungarian',
    'Norwegian',
    'Vietnamese'
  ];

  // --- Universal File Picker ---
  Future<void> _pickVideoFile() async {
    FilePickerResult? result = await FilePicker.platform.pickFiles(
      type: FileType.video,
      withData: true,
    );

    if (result != null && result.files.isNotEmpty) {
      setState(() {
        _selectedFile = result.files.first;
        _statusMessage = "📁 Selected Video: ${_selectedFile!.name}";
      });
    } else {
      setState(() {
        _statusMessage = "❌ No video selected.";
      });
    }
  }

  // --- Universal Backend Request ---
  Future<void> sendToBackend() async {
    if (_selectedFile == null) {
      setState(() {
        _statusMessage =
            "❌ Please click the box above and select a video file first!";
      });
      return;
    }

    if (_targetLanguage == null) {
      setState(() {
        _statusMessage = "❌ Please select a target language first!";
      });
      return;
    }

    setState(() {
      _isLoading = true;
      _statusMessage =
          "📡 Uploading & processing AI Pipeline (Demucs, Whisper, ElevenLabs)...";
      _isCompleted = false;
    });

    // NOTE: Jab phone par test karega, tab '127.0.0.1' ki jagah apne PC ka Local IP (jaise '192.168.1.5') daalna padega.
    var url = Uri.parse('http://127.0.0.1:8000/translate');

    try {
      var request = http.MultipartRequest('POST', url);

      request.fields['original_language'] = _originalLanguage;
      request.fields['target_language'] = _targetLanguage!;

      if (kIsWeb) {
        if (_selectedFile!.bytes != null) {
          request.files.add(
            http.MultipartFile.fromBytes(
              'file',
              _selectedFile!.bytes!,
              filename: _selectedFile!.name,
            ),
          );
        }
      } else {
        if (_selectedFile!.path != null) {
          request.files.add(
            await http.MultipartFile.fromPath(
              'file',
              _selectedFile!.path!,
            ),
          );
        }
      }

      var streamedResponse = await request.send();
      var response = await http.Response.fromStream(streamedResponse);

      if (response.statusCode == 200) {
        setState(() {
          _statusMessage =
              "✅ SUCCESS: Video dubbed, lip-synced, and ready for download!";
          _isCompleted = true;
        });
      } else {
        setState(() {
          _statusMessage =
              "❌ SERVER ERROR: ${response.statusCode} - ${response.body}";
          _isCompleted = false;
        });
      }
    } catch (e) {
      setState(() {
        _statusMessage =
            "❌ CONNECTION FAILED: Is Python FastAPI server running? Error: $e";
        _isCompleted = false;
      });
    } finally {
      setState(() {
        _isLoading = false;
      });
    }
  }

  // --- Cross-Platform Download Function (Web & Phone dono ke liye safe) ---
  Future<void> _downloadVideo() async {
    final Uri downloadUri = Uri.parse('http://127.0.0.1:8000/download-video');

    try {
      if (await canLaunchUrl(downloadUri)) {
        await launchUrl(
          downloadUri,
          mode: LaunchMode
              .externalApplication, // Phone aur Browser dono mein external browser/downloader open karega
        );
      } else {
        setState(() {
          _statusMessage = "❌ Could not open download link.";
        });
      }
    } catch (e) {
      setState(() {
        _statusMessage = "❌ Download Error: $e";
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text("Neural Voice-Match Dubber Studio"),
        backgroundColor: Colors.deepPurple,
        foregroundColor: Colors.white,
      ),
      body: Center(
        child: Container(
          constraints: const BoxConstraints(maxWidth: 700),
          padding: const EdgeInsets.all(24.0),
          child: ListView(
            children: [
              const Text(
                "AI Video Translation & Dubbing Studio",
                style: TextStyle(
                    fontSize: 22,
                    fontWeight: FontWeight.bold,
                    color: Colors.deepPurple),
                textAlign: TextAlign.center,
              ),
              const SizedBox(height: 24),

              // --- Video Selection Box ---
              InkWell(
                onTap: _pickVideoFile,
                borderRadius: BorderRadius.circular(4),
                child: InputDecorator(
                  decoration: const InputDecoration(
                    labelText: "Select Video File",
                    border: OutlineInputBorder(),
                    prefixIcon:
                        Icon(Icons.video_file, color: Colors.deepPurple),
                    suffixIcon: Icon(Icons.folder_open),
                  ),
                  child: Text(
                    _selectedFile == null
                        ? "Click here to browse and select a video..."
                        : _selectedFile!.name,
                    style: TextStyle(
                      fontSize: 15,
                      color: _selectedFile == null
                          ? Colors.grey[600]
                          : Colors.black87,
                    ),
                    overflow: TextOverflow.ellipsis,
                  ),
                ),
              ),
              const SizedBox(height: 20),

              // --- Original Language Dropdown ---
              DropdownButtonFormField<String>(
                value: _originalLanguage,
                decoration: const InputDecoration(
                  labelText: "Original Language",
                  border: OutlineInputBorder(),
                  prefixIcon: Icon(Icons.language),
                ),
                items: elevenLabsLanguages.map((String lang) {
                  return DropdownMenuItem<String>(
                    value: lang,
                    child: Text(lang),
                  );
                }).toList(),
                onChanged: (String? newValue) {
                  setState(() {
                    _originalLanguage = newValue!;
                  });
                },
              ),
              const SizedBox(height: 20),

              // --- Target Language Dropdown with Hint ---
              DropdownButtonFormField<String>(
                value: _targetLanguage,
                hint: const Text("Select target language"),
                decoration: const InputDecoration(
                  labelText: "Target Dubbing Language",
                  border: OutlineInputBorder(),
                  prefixIcon: Icon(Icons.translate),
                ),
                items: elevenLabsLanguages
                    .where((l) => l != 'Auto-Detect')
                    .map((String lang) {
                  return DropdownMenuItem<String>(
                    value: lang,
                    child: Text(lang),
                  );
                }).toList(),
                onChanged: (String? newValue) {
                  setState(() {
                    _targetLanguage = newValue;
                  });
                },
              ),
              const SizedBox(height: 30),

              // --- Run Button ---
              ElevatedButton(
                onPressed: _isLoading ? null : sendToBackend,
                style: ElevatedButton.styleFrom(
                  padding: const EdgeInsets.symmetric(vertical: 18),
                  backgroundColor: Colors.deepPurple,
                  foregroundColor: Colors.white,
                ),
                child: _isLoading
                    ? const Row(
                        mainAxisAlignment: MainAxisAlignment.center,
                        children: [
                          SizedBox(
                            width: 22,
                            height: 22,
                            child: CircularProgressIndicator(
                                color: Colors.white, strokeWidth: 2.5),
                          ),
                          SizedBox(width: 12),
                          Text("Processing AI Pipeline...",
                              style: TextStyle(fontSize: 18)),
                        ],
                      )
                    : const Text(
                        "Run Neural Voice-Match Dubber",
                        style: TextStyle(
                            fontSize: 18, fontWeight: FontWeight.bold),
                      ),
              ),
              const SizedBox(height: 24),

              // --- Status Display ---
              if (_statusMessage.isNotEmpty)
                Container(
                  padding: const EdgeInsets.all(16),
                  decoration: BoxDecoration(
                    color: Colors.grey[100],
                    border: Border.all(color: Colors.grey.shade300),
                    borderRadius: BorderRadius.circular(8),
                  ),
                  child: Text(
                    _statusMessage,
                    style: const TextStyle(
                        fontSize: 14, fontWeight: FontWeight.w500, height: 1.4),
                    textAlign: TextAlign.center,
                  ),
                ),
              const SizedBox(height: 24),

              // --- Download Button ---
              if (_isCompleted)
                ElevatedButton.icon(
                  onPressed: _downloadVideo,
                  icon: const Icon(Icons.download),
                  label: const Text("Download Final Dubbed Video",
                      style: TextStyle(fontSize: 16)),
                  style: ElevatedButton.styleFrom(
                    padding: const EdgeInsets.symmetric(vertical: 16),
                    backgroundColor: Colors.green,
                    foregroundColor: Colors.white,
                  ),
                ),
            ],
          ),
        ),
      ),
    );
  }
}
