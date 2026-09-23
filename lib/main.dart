import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;
import 'package:file_picker/file_picker.dart';
import 'dart:convert';
import 'package:url_launcher/url_launcher.dart';

void main() {
  runApp(const MyApp());
}

class MyApp extends StatelessWidget {
  const MyApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'AI HD Dubbing & Lip-Sync Studio',
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

  String? _originalLanguage;
  String? _targetLanguage;
  String? _sessionId; // Track session ID for backend synchronization

  bool _skipReview = false;
  bool _isLoading = false;
  String _statusMessage = '';

  String _currentStage = 'select'; // 'select', 'processing_dub', 'completed'

  // 👇 APNE REMOTE SERVER KA IP YAHAN DAALO (jaise http://13.23.45.67:8000)
  final String serverUrl = 'http://<YOUR_SERVER_PUBLIC_IP>:8000';

  final List<String> elevenLabsLanguages = [
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

  Future<void> _pickVideoFile() async {
    FilePickerResult? result = await FilePicker.platform.pickFiles(
      type: FileType.video,
      withData: true,
    );

    if (result != null && result.files.isNotEmpty) {
      setState(() {
        _selectedFile = result.files.first;
        _sessionId = null;
        _statusMessage = "📁 Selected Video: ${_selectedFile!.name}";
        _currentStage = 'select';
      });
    } else {
      setState(() {
        _statusMessage = "❌ No video selected.";
      });
    }
  }

  Future<void> processVideo() async {
    if (_selectedFile == null) {
      setState(() => _statusMessage = "❌ Please select a video file first!");
      return;
    }

    if (_originalLanguage == null || _originalLanguage!.isEmpty) {
      setState(() => _statusMessage = "❌ Please select an original language!");
      return;
    }

    if (_targetLanguage == null || _targetLanguage!.isEmpty) {
      setState(() => _statusMessage = "❌ Please select a target language!");
      return;
    }

    setState(() {
      _isLoading = true;
      // Simple and clean user-facing status message (No deep technical details)
      _statusMessage = _skipReview
          ? "🚀 Processing AI Video Pipeline..."
          : "⏳ Preparing your video, please wait...";
    });

    var url = Uri.parse('$serverUrl/process-video');

    try {
      var request = http.MultipartRequest('POST', url);
      request.fields['original_language'] = _originalLanguage!;
      request.fields['target_language'] = _targetLanguage!;
      request.fields['skip_review'] = _skipReview.toString();

      if (kIsWeb && _selectedFile!.bytes != null) {
        request.files.add(http.MultipartFile.fromBytes(
            'file', _selectedFile!.bytes!,
            filename: _selectedFile!.name));
      } else if (_selectedFile!.path != null) {
        request.files.add(
            await http.MultipartFile.fromPath('file', _selectedFile!.path!));
      }

      // Timeout added (10 mins)
      var streamedResponse =
          await request.send().timeout(const Duration(minutes: 10));
      var response = await http.Response.fromStream(streamedResponse);

      if (response.statusCode == 200) {
        var data = jsonDecode(response.body);
        _sessionId = data['session_id'];

        if (_skipReview) {
          setState(() {
            _currentStage = 'completed';
            _statusMessage = "✅ SUCCESS: Full HD Dubbed Video is ready!";
          });
        } else {
          final updatedOriginalTranscript = await Navigator.push<List<dynamic>>(
            context,
            MaterialPageRoute(
              builder: (context) => TranscriptEditorScreen(
                speakers: Map<String, dynamic>.from(data['speakers'] ?? {}),
                transcript: List<dynamic>.from(data['transcript'] ?? []),
              ),
            ),
          );

          if (updatedOriginalTranscript != null) {
            await fetchTranslation(jsonEncode(updatedOriginalTranscript));
          } else {
            setState(() {
              _statusMessage = "⚠️ Review cancelled.";
              _isLoading = false;
            });
          }
        }
      } else {
        setState(() => _statusMessage =
            "❌ SERVER ERROR: ${response.statusCode} - ${response.body}");
      }
    } catch (e) {
      setState(() => _statusMessage = "❌ CONNECTION FAILED: $e");
    } finally {
      if (!_skipReview && _currentStage != 'completed') {
        setState(() => _isLoading = false);
      }
    }
  }

  Future<void> fetchTranslation(String editedOriginalJson) async {
    setState(() {
      _isLoading = true;
      // Clean and smooth message
      _statusMessage = "🌐 Translating text...";
    });

    var url = Uri.parse('$serverUrl/translate-edited');

    try {
      var response = await http.post(
        url,
        body: {
          'original_language': _originalLanguage!,
          'target_language': _targetLanguage!,
          'final_text': editedOriginalJson,
        },
      ).timeout(const Duration(minutes: 2));

      if (response.statusCode == 200) {
        var data = jsonDecode(response.body);
        List<dynamic> translatedTranscript = data['translated_transcript'];

        final finalEditedTranslation = await Navigator.push<List<dynamic>>(
          context,
          MaterialPageRoute(
            builder: (context) => TranslationEditorScreen(
              transcript: translatedTranscript,
            ),
          ),
        );

        if (finalEditedTranslation != null) {
          await generateFinalDub(jsonEncode(finalEditedTranslation));
        } else {
          setState(() {
            _statusMessage = "⚠️ Translation review cancelled.";
            _isLoading = false;
          });
        }
      } else {
        setState(
            () => _statusMessage = "❌ Translation Error: ${response.body}");
      }
    } catch (e) {
      setState(() => _statusMessage = "❌ Connection Error: $e");
    } finally {
      setState(() => _isLoading = false);
    }
  }

  Future<void> generateFinalDub(String editedTranslationJson) async {
    setState(() {
      _isLoading = true;
      _currentStage = 'processing_dub';
      // Professional, clean message without showing deep underlying pipeline terms
      _statusMessage =
          "⚙️ Generating final AI dubbed video...\nPlease wait patiently, this may take a few minutes.";
    });

    var url = Uri.parse('$serverUrl/generate-dub');

    try {
      var request = http.MultipartRequest('POST', url);
      request.fields['original_language'] = _originalLanguage!;
      request.fields['target_language'] = _targetLanguage!;
      request.fields['final_text'] = editedTranslationJson;
      if (_sessionId != null) {
        request.fields['session_id'] = _sessionId!;
      }

      if (kIsWeb && _selectedFile!.bytes != null) {
        request.files.add(http.MultipartFile.fromBytes(
            'file', _selectedFile!.bytes!,
            filename: _selectedFile!.name));
      } else if (_selectedFile!.path != null) {
        request.files.add(
            await http.MultipartFile.fromPath('file', _selectedFile!.path!));
      }

      // Timeout added (30 mins for heavy AI processing)
      var streamedResponse =
          await request.send().timeout(const Duration(minutes: 30));
      var response = await http.Response.fromStream(streamedResponse);

      if (response.statusCode == 200) {
        var data = jsonDecode(response.body);
        if (data['session_id'] != null) {
          _sessionId = data['session_id'];
        }
        setState(() {
          _currentStage = 'completed';
          _statusMessage =
              "✅ SUCCESS: Full HD Lip-Synced video is ready for download!";
        });
      } else {
        setState(() {
          _currentStage = 'select';
          _statusMessage = "❌ ERROR: ${response.statusCode} - ${response.body}";
        });
      }
    } catch (e) {
      setState(() {
        _currentStage = 'select';
        _statusMessage = "❌ CONNECTION FAILED: $e";
      });
    } finally {
      setState(() => _isLoading = false);
    }
  }

  Future<void> _downloadVideo() async {
    final Uri downloadUri = Uri.parse(
      _sessionId != null
          ? '$serverUrl/download-video?session_id=$_sessionId'
          : '$serverUrl/download-video',
    );
    try {
      if (await canLaunchUrl(downloadUri)) {
        await launchUrl(downloadUri, mode: LaunchMode.externalApplication);
      } else {
        setState(() => _statusMessage = "❌ Could not open download link.");
      }
    } catch (e) {
      setState(() => _statusMessage = "❌ Download Error: $e");
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text("AI HD Dubbing & Lip-Sync Studio"),
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
                "AI Video Translation, Voice Clone & Lip-Sync",
                style: TextStyle(
                    fontSize: 22,
                    fontWeight: FontWeight.bold,
                    color: Colors.deepPurple),
                textAlign: TextAlign.center,
              ),
              const SizedBox(height: 24),
              if (_currentStage == 'select' ||
                  _currentStage == 'processing_dub') ...[
                InkWell(
                  onTap: _isLoading ? null : _pickVideoFile,
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
                              : Colors.black87),
                      overflow: TextOverflow.ellipsis,
                    ),
                  ),
                ),
                const SizedBox(height: 20),
                DropdownButtonFormField<String>(
                  value: _originalLanguage,
                  hint: const Text("Select original language"),
                  decoration: const InputDecoration(
                      labelText: "Original Language",
                      border: OutlineInputBorder(),
                      prefixIcon: Icon(Icons.language)),
                  items: elevenLabsLanguages
                      .map((l) => DropdownMenuItem(value: l, child: Text(l)))
                      .toList(),
                  onChanged: _isLoading
                      ? null
                      : (val) => setState(() => _originalLanguage = val),
                ),
                const SizedBox(height: 20),
                DropdownButtonFormField<String>(
                  value: _targetLanguage,
                  hint: const Text("Select target language"),
                  decoration: const InputDecoration(
                      labelText: "Target Dubbing Language",
                      border: OutlineInputBorder(),
                      prefixIcon: Icon(Icons.translate)),
                  items: elevenLabsLanguages
                      .map((l) => DropdownMenuItem(value: l, child: Text(l)))
                      .toList(),
                  onChanged: _isLoading
                      ? null
                      : (val) => setState(() => _targetLanguage = val),
                ),
                const SizedBox(height: 12),
                CheckboxListTile(
                  title: const Text(
                      "Skip text review and generate video directly"),
                  subtitle: const Text(
                      "Bypasses manual text verification and runs the full pipeline."),
                  value: _skipReview,
                  activeColor: Colors.deepPurple,
                  controlAffinity: ListTileControlAffinity.leading,
                  contentPadding: EdgeInsets.zero,
                  onChanged: _isLoading
                      ? null
                      : (bool? value) {
                          setState(() {
                            _skipReview = value ?? false;
                          });
                        },
                ),
                const SizedBox(height: 20),
                ElevatedButton(
                  onPressed: _isLoading ? null : processVideo,
                  style: ElevatedButton.styleFrom(
                      padding: const EdgeInsets.symmetric(vertical: 18),
                      backgroundColor: Colors.deepPurple,
                      foregroundColor: Colors.white),
                  child: _isLoading
                      ? Row(
                          mainAxisAlignment: MainAxisAlignment.center,
                          children: [
                            const SizedBox(
                                width: 22,
                                height: 22,
                                child: CircularProgressIndicator(
                                    color: Colors.white, strokeWidth: 2.5)),
                            const SizedBox(width: 12),
                            Text(
                              _currentStage == 'processing_dub'
                                  ? "Processing Video..."
                                  : "Please Wait...",
                              style: const TextStyle(fontSize: 18),
                            ),
                          ],
                        )
                      : Text(
                          _skipReview
                              ? "Generate Final HD Dubbed Video Directly"
                              : "Step 1: Review & Edit Original Transcript",
                          style: const TextStyle(
                              fontSize: 18, fontWeight: FontWeight.bold),
                        ),
                ),
              ],
              const SizedBox(height: 24),
              if (_statusMessage.isNotEmpty)
                Container(
                  padding: const EdgeInsets.all(16),
                  decoration: BoxDecoration(
                    color: Colors.grey[100],
                    border: Border.all(color: Colors.deepPurple.shade200),
                    borderRadius: BorderRadius.circular(8),
                  ),
                  child: Text(_statusMessage,
                      style: const TextStyle(
                          fontSize: 14,
                          fontWeight: FontWeight.w500,
                          height: 1.5,
                          color: Colors.deepPurple),
                      textAlign: TextAlign.center),
                ),
              const SizedBox(height: 24),
              if (_currentStage == 'completed')
                ElevatedButton.icon(
                  onPressed: _downloadVideo,
                  icon: const Icon(Icons.download),
                  label: const Text("Download Final HD Dubbed Video",
                      style: TextStyle(fontSize: 16)),
                  style: ElevatedButton.styleFrom(
                      padding: const EdgeInsets.symmetric(vertical: 16),
                      backgroundColor: Colors.green,
                      foregroundColor: Colors.white),
                ),
              if (_currentStage == 'completed')
                Padding(
                  padding: const EdgeInsets.only(top: 16.0),
                  child: TextButton.icon(
                      onPressed: () {
                        setState(() {
                          _currentStage = 'select';
                          _selectedFile = null;
                          _statusMessage = '';
                        });
                      },
                      icon: const Icon(Icons.refresh),
                      label: const Text("Process Another Video")),
                )
            ],
          ),
        ),
      ),
    );
  }
}

// =====================================================================
// STEP 1: ORIGINAL TRANSCRIPT EDITOR SCREEN
// =====================================================================
class TranscriptEditorScreen extends StatefulWidget {
  final Map<String, dynamic> speakers;
  final List<dynamic> transcript;

  const TranscriptEditorScreen({
    super.key,
    required this.speakers,
    required this.transcript,
  });

  @override
  State<TranscriptEditorScreen> createState() => _TranscriptEditorScreenState();
}

class _TranscriptEditorScreenState extends State<TranscriptEditorScreen> {
  late List<Map<String, dynamic>> _editableTranscript;
  final Map<String, Color> _speakerColors = {};
  final List<Color> _palette = [
    Colors.blue,
    Colors.orange,
    Colors.teal,
    Colors.pink,
    Colors.amber,
    Colors.indigo,
    Colors.cyan,
    Colors.deepOrange
  ];

  @override
  void initState() {
    super.initState();
    _editableTranscript = widget.transcript
        .map((item) => Map<String, dynamic>.from(item))
        .toList();

    int colorIndex = 0;
    for (var speaker in widget.speakers.keys) {
      _speakerColors[speaker] = _palette[colorIndex % _palette.length];
      colorIndex++;
    }
  }

  String _formatTime(double seconds) {
    int mins = (seconds ~/ 60);
    int secs = (seconds % 60).toInt();
    return "${mins.toString().padLeft(2, '0')}:${secs.toString().padLeft(2, '0')}";
  }

  void _editOriginalText(int index) {
    final controller = TextEditingController(
        text: _editableTranscript[index]['original_text']);

    showDialog(
      context: context,
      builder: (context) => AlertDialog(
        title: Text(
            "Edit Original Text (${_editableTranscript[index]['speaker']})"),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text(
              "⚠️ Note: Keep edits minimal to avoid sync mismatch.",
              style: TextStyle(fontSize: 12, color: Colors.redAccent),
            ),
            const SizedBox(height: 12),
            TextField(
              controller: controller,
              maxLines: 4,
              decoration: const InputDecoration(
                border: OutlineInputBorder(),
                labelText: "Original Text",
              ),
            ),
          ],
        ),
        actions: [
          TextButton(
              onPressed: () => Navigator.pop(context),
              child: const Text("Cancel")),
          ElevatedButton(
            style: ElevatedButton.styleFrom(
                backgroundColor: Colors.deepPurple,
                foregroundColor: Colors.white),
            onPressed: () {
              setState(() {
                _editableTranscript[index]['original_text'] =
                    controller.text.trim();
              });
              Navigator.pop(context);
            },
            child: const Text("Save"),
          ),
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text("Step 1: Review Original Transcript"),
        backgroundColor: Colors.deepPurple,
        foregroundColor: Colors.white,
      ),
      body: Column(
        children: [
          Container(
            padding: const EdgeInsets.all(12),
            color: Colors.deepPurple.shade50,
            child: const Text(
              "💡 Verify text before GPT translates it.",
              style: TextStyle(fontSize: 13, color: Colors.deepPurple),
              textAlign: TextAlign.center,
            ),
          ),
          Expanded(
            child: ListView.builder(
              padding: const EdgeInsets.all(16),
              itemCount: _editableTranscript.length,
              itemBuilder: (context, index) {
                final item = _editableTranscript[index];
                final speaker = item['speaker'] ?? 'Speaker';
                final startTime =
                    _formatTime((item['start'] ?? 0.0).toDouble());
                final endTime = _formatTime((item['end'] ?? 0.0).toDouble());
                final originalText = item['original_text'] ?? '';
                final base64Image = widget.speakers[speaker];
                final speakerColor =
                    _speakerColors[speaker] ?? Colors.deepPurple;
                final firstLetter =
                    speaker.isNotEmpty ? speaker[0].toUpperCase() : 'S';

                return Card(
                  margin: const EdgeInsets.only(bottom: 16),
                  elevation: 3,
                  shape: RoundedRectangleBorder(
                      borderRadius: BorderRadius.circular(12)),
                  child: InkWell(
                    onTap: () => _editOriginalText(index),
                    borderRadius: BorderRadius.circular(12),
                    child: Padding(
                      padding: const EdgeInsets.all(16.0),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Row(
                            children: [
                              ClipOval(
                                child: SizedBox(
                                  width: 40,
                                  height: 40,
                                  child: base64Image != null &&
                                          base64Image.isNotEmpty
                                      ? Image.memory(
                                          base64Decode(base64Image),
                                          fit: BoxFit.cover,
                                          errorBuilder:
                                              (context, error, stackTrace) =>
                                                  Container(
                                            color: speakerColor,
                                            alignment: Alignment.center,
                                            child: Text(firstLetter,
                                                style: const TextStyle(
                                                    color: Colors.white,
                                                    fontWeight:
                                                        FontWeight.bold)),
                                          ),
                                        )
                                      : Container(
                                          color: speakerColor,
                                          alignment: Alignment.center,
                                          child: Text(firstLetter,
                                              style: const TextStyle(
                                                  color: Colors.white,
                                                  fontWeight: FontWeight.bold)),
                                        ),
                                ),
                              ),
                              const SizedBox(width: 12),
                              Expanded(
                                child: Column(
                                  crossAxisAlignment: CrossAxisAlignment.start,
                                  children: [
                                    Text(speaker,
                                        style: const TextStyle(
                                            fontWeight: FontWeight.bold,
                                            fontSize: 16)),
                                    const SizedBox(height: 2),
                                    Text("$startTime - $endTime",
                                        style: TextStyle(
                                            color: Colors.grey[600],
                                            fontSize: 13)),
                                  ],
                                ),
                              ),
                            ],
                          ),
                          const Divider(height: 24),
                          Row(
                            mainAxisAlignment: MainAxisAlignment.spaceBetween,
                            children: const [
                              Text("Original Text (Tap to Edit):",
                                  style: TextStyle(
                                      fontSize: 12,
                                      fontWeight: FontWeight.bold,
                                      color: Colors.deepPurple)),
                              Icon(Icons.edit,
                                  size: 16, color: Colors.deepPurple),
                            ],
                          ),
                          const SizedBox(height: 6),
                          Container(
                            width: double.infinity,
                            padding: const EdgeInsets.all(12),
                            decoration: BoxDecoration(
                              color: Colors.white,
                              border:
                                  Border.all(color: Colors.deepPurple.shade200),
                              borderRadius: BorderRadius.circular(8),
                            ),
                            child: Text(originalText,
                                style: const TextStyle(
                                    color: Colors.black87,
                                    fontSize: 15,
                                    fontWeight: FontWeight.w500)),
                          ),
                        ],
                      ),
                    ),
                  ),
                );
              },
            ),
          ),
          Container(
            padding: const EdgeInsets.all(16),
            decoration: BoxDecoration(
              color: Colors.white,
              boxShadow: [
                BoxShadow(
                    color: Colors.black.withOpacity(0.05),
                    blurRadius: 10,
                    offset: const Offset(0, -5))
              ],
            ),
            child: SizedBox(
              width: double.infinity,
              child: ElevatedButton(
                style: ElevatedButton.styleFrom(
                  backgroundColor: Colors.deepPurple,
                  foregroundColor: Colors.white,
                  padding: const EdgeInsets.symmetric(vertical: 16),
                  shape: RoundedRectangleBorder(
                      borderRadius: BorderRadius.circular(8)),
                ),
                onPressed: () => Navigator.pop(context, _editableTranscript),
                child: const Text("Next: Translate Edited Text via GPT",
                    style:
                        TextStyle(fontSize: 18, fontWeight: FontWeight.bold)),
              ),
            ),
          ),
        ],
      ),
    );
  }
}

// =====================================================================
// STEP 2: TRANSLATION EDITOR SCREEN
// =====================================================================
class TranslationEditorScreen extends StatefulWidget {
  final List<dynamic> transcript;

  const TranslationEditorScreen({
    super.key,
    required this.transcript,
  });

  @override
  State<TranslationEditorScreen> createState() =>
      _TranslationEditorScreenState();
}

class _TranslationEditorScreenState extends State<TranslationEditorScreen> {
  late List<Map<String, dynamic>> _editableTranscript;

  @override
  void initState() {
    super.initState();
    _editableTranscript = widget.transcript
        .map((item) => Map<String, dynamic>.from(item))
        .toList();
  }

  void _editTranslationText(int index) {
    final controller = TextEditingController(
        text: _editableTranscript[index]['translated_text']);

    showDialog(
      context: context,
      builder: (context) => AlertDialog(
        title:
            Text("Edit Translation (${_editableTranscript[index]['speaker']})"),
        content: TextField(
          controller: controller,
          maxLines: 4,
          decoration: const InputDecoration(
            border: OutlineInputBorder(),
            labelText: "Translated Text",
          ),
        ),
        actions: [
          TextButton(
              onPressed: () => Navigator.pop(context),
              child: const Text("Cancel")),
          ElevatedButton(
            style: ElevatedButton.styleFrom(
                backgroundColor: Colors.deepPurple,
                foregroundColor: Colors.white),
            onPressed: () {
              setState(() {
                _editableTranscript[index]['translated_text'] =
                    controller.text.trim();
              });
              Navigator.pop(context);
            },
            child: const Text("Save"),
          ),
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text("Step 2: Review & Edit Translation"),
        backgroundColor: Colors.deepPurple,
        foregroundColor: Colors.white,
      ),
      body: Column(
        children: [
          Container(
            padding: const EdgeInsets.all(12),
            color: Colors.green.shade50,
            child: const Text(
              "💡 Finalize translation before generating the final video.",
              style: TextStyle(fontSize: 13, color: Colors.green),
              textAlign: TextAlign.center,
            ),
          ),
          Expanded(
            child: ListView.builder(
              padding: const EdgeInsets.all(16),
              itemCount: _editableTranscript.length,
              itemBuilder: (context, index) {
                final item = _editableTranscript[index];
                final speaker = item['speaker'] ?? 'Speaker';
                final originalText = item['original_text'] ?? '';
                final translatedText = item['translated_text'] ?? '';

                return Card(
                  margin: const EdgeInsets.only(bottom: 16),
                  elevation: 3,
                  shape: RoundedRectangleBorder(
                      borderRadius: BorderRadius.circular(12)),
                  child: InkWell(
                    onTap: () => _editTranslationText(index),
                    borderRadius: BorderRadius.circular(12),
                    child: Padding(
                      padding: const EdgeInsets.all(16.0),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            speaker,
                            style: const TextStyle(
                                fontWeight: FontWeight.bold,
                                fontSize: 16,
                                color: Colors.deepPurple),
                          ),
                          const Divider(height: 24),
                          const Text(
                            "Original Text:",
                            style: TextStyle(
                                fontSize: 12,
                                fontWeight: FontWeight.bold,
                                color: Colors.grey),
                          ),
                          const SizedBox(height: 4),
                          Text(
                            originalText,
                            style: TextStyle(
                                fontSize: 14, color: Colors.grey[800]),
                          ),
                          const SizedBox(height: 16),
                          Row(
                            mainAxisAlignment: MainAxisAlignment.spaceBetween,
                            children: const [
                              Text(
                                "Translated Text (Tap to Edit):",
                                style: TextStyle(
                                    fontSize: 12,
                                    fontWeight: FontWeight.bold,
                                    color: Colors.green),
                              ),
                              Icon(Icons.edit, size: 16, color: Colors.green),
                            ],
                          ),
                          const SizedBox(height: 6),
                          Container(
                            width: double.infinity,
                            padding: const EdgeInsets.all(12),
                            decoration: BoxDecoration(
                              color: Colors.white,
                              border: Border.all(color: Colors.green.shade200),
                              borderRadius: BorderRadius.circular(8),
                            ),
                            child: Text(
                              translatedText,
                              style: const TextStyle(
                                  color: Colors.black87,
                                  fontSize: 15,
                                  fontWeight: FontWeight.w500),
                            ),
                          ),
                        ],
                      ),
                    ),
                  ),
                );
              },
            ),
          ),
          Container(
            padding: const EdgeInsets.all(16),
            decoration: BoxDecoration(
              color: Colors.white,
              boxShadow: [
                BoxShadow(
                    color: Colors.black.withOpacity(0.05),
                    blurRadius: 10,
                    offset: const Offset(0, -5))
              ],
            ),
            child: SizedBox(
              width: double.infinity,
              child: ElevatedButton(
                style: ElevatedButton.styleFrom(
                  backgroundColor: Colors.green,
                  foregroundColor: Colors.white,
                  padding: const EdgeInsets.symmetric(vertical: 16),
                  shape: RoundedRectangleBorder(
                      borderRadius: BorderRadius.circular(8)),
                ),
                onPressed: () => Navigator.pop(context, _editableTranscript),
                child: const Text("Generate Final HD Dubbed Video",
                    style:
                        TextStyle(fontSize: 18, fontWeight: FontWeight.bold)),
              ),
            ),
          ),
        ],
      ),
    );
  }
}
